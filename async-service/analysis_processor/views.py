"""
Views for асинхронной обработки заявок на спектральный анализ.
"""
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

import time
import random
import requests
from concurrent import futures

# URL основного сервиса для отправки результатов
MAIN_SERVICE_URL = "http://localhost:8080/api/spectrum-analysis"
API_KEY = "secret12345678"  # 8 байт ключ для псевдо-авторизации

# Пул потоков для асинхронного выполнения задач
executor = futures.ThreadPoolExecutor(max_workers=1)


def parse_spectrum(spectrum_str):
    """
    Парсит спектр из формата "400,25;450,65;500,45;550,35;600,70;650,55"
    в список кортежей (длина_волны, интенсивность).

    Args:
        spectrum_str: Строка спектра в формате "wavelength,intensity;wavelength,intensity;..."

    Returns:
        list: Список кортежей [(wavelength, intensity), ...]
    """
    if not spectrum_str or not spectrum_str.strip():
        return []

    spectrum_points = []
    try:
        # Разделяем по точкам с запятой
        pairs = spectrum_str.split(';')
        for pair in pairs:
            pair = pair.strip()
            if not pair:
                continue
            # Разделяем по запятой
            parts = pair.split(',')
            if len(parts) == 2:
                wavelength = float(parts[0].strip())
                intensity = float(parts[1].strip())
                spectrum_points.append((wavelength, intensity))
    except (ValueError, AttributeError) as e:
        print(f"[Async Service] Ошибка парсинга спектра: {e}")
        return []

    return spectrum_points


def calculate_spectrum_similarity(analysis_spectrum, pigment_spectrum):
    """
    Вычисляет корреляцию (схожесть) между спектром заявки и спектром пигмента.

    Использует метод корреляции Пирсона на интерполированных значениях.

    Args:
        analysis_spectrum: Список кортежей (длина_волны, интенсивность) спектра заявки
        pigment_spectrum: Список кортежей (длина_волны, интенсивность) спектра пигмента

    Returns:
        float: Коэффициент корреляции от -1 до 1 (1 = идеальное совпадение)
    """
    if not analysis_spectrum or not pigment_spectrum:
        return 0.0

    # Создаем словари для быстрого доступа по длине волны
    analysis_dict = {wavelength: intensity for wavelength, intensity in analysis_spectrum}
    pigment_dict = {wavelength: intensity for wavelength, intensity in pigment_spectrum}

    # Находим общие длины волн
    common_wavelengths = set(analysis_dict.keys()) & set(pigment_dict.keys())

    if not common_wavelengths:
        # Если нет общих длин волн, интерполируем значения
        all_wavelengths = sorted(set(analysis_dict.keys()) | set(pigment_dict.keys()))
        common_wavelengths = all_wavelengths

    # Интерполируем значения для общих длин волн
    analysis_values = []
    pigment_values = []

    for wl in sorted(common_wavelengths):
        # Значение из анализа (или интерполяция)
        if wl in analysis_dict:
            a_val = analysis_dict[wl]
        else:
            # Интерполяция: берем ближайшие значения
            closest = min(analysis_dict.keys(), key=lambda x: abs(x - wl))
            a_val = analysis_dict[closest] * 0.5  # Упрощенная интерполяция

        # Значение из спектра пигмента (или интерполяция)
        if wl in pigment_dict:
            p_val = pigment_dict[wl]
        else:
            # Интерполяция
            closest = min(pigment_dict.keys(), key=lambda x: abs(x - wl))
            p_val = pigment_dict[closest] * 0.5

        analysis_values.append(a_val)
        pigment_values.append(p_val)

    if len(analysis_values) < 2 or len(pigment_values) < 2:
        return 0.0

    # Вычисляем корреляцию Пирсона
    n = len(analysis_values)
    mean_a = sum(analysis_values) / n
    mean_p = sum(pigment_values) / n

    numerator = sum((analysis_values[i] - mean_a) * (pigment_values[i] - mean_p) for i in range(n))
    denominator_a = sum((analysis_values[i] - mean_a) ** 2 for i in range(n))
    denominator_p = sum((pigment_values[i] - mean_p) ** 2 for i in range(n))

    if denominator_a == 0 or denominator_p == 0:
        return 0.0

    correlation = numerator / ((denominator_a ** 0.5) * (denominator_p ** 0.5))

    # Нормализуем к [0, 1] (1 = полное совпадение, 0 = нет совпадения)
    return max(0.0, correlation)


def calculate_pigment_percentages_from_spectrum(analysis_spectrum, pigment_spectra):
    """
    Рассчитывает проценты пигментов на основе сравнения спектров.

    Алгоритм:
    1. Для каждого пигмента вычисляем корреляцию его спектра со спектром заявки
    2. Распределяем проценты пропорционально коэффициентам корреляции
    3. Нормализуем, чтобы сумма была 100%

    Args:
        analysis_spectrum: Список кортежей (длина_волны, интенсивность) спектра заявки
        pigment_spectra: Список словарей {"id": int, "spectrum": str} со спектрами пигментов

    Returns:
        dict: Словарь {pigment_id: percent}
    """
    if not analysis_spectrum or not pigment_spectra:
        # Равномерное распределение, если нет данных
        num = len(pigment_spectra) if pigment_spectra else 1
        return {p["id"]: round(100.0 / num, 2) for p in pigment_spectra} if pigment_spectra else {}

    # Вычисляем корреляцию для каждого пигмента
    correlations = {}
    for pigment_data in pigment_spectra:
        pigment_id = pigment_data.get("id")
        pigment_spectrum_str = pigment_data.get("spectrum", "")

        if not pigment_spectrum_str:
            # Если у пигмента нет спектра, используем минимальную корреляцию
            correlations[pigment_id] = 0.1
            continue

        # Парсим спектр пигмента
        pigment_spectrum_points = parse_spectrum(pigment_spectrum_str)
        if not pigment_spectrum_points:
            correlations[pigment_id] = 0.1
            continue

        # Вычисляем корреляцию
        correlation = calculate_spectrum_similarity(analysis_spectrum, pigment_spectrum_points)
        # Минимальное значение 0.1 для пигментов без спектра или с низкой корреляцией
        final_correlation = max(0.1, correlation)
        correlations[pigment_id] = final_correlation
        print(f"[Async Service]   Пигмент {pigment_id}: корреляция={correlation:.3f} → {final_correlation:.3f} (с минимумом)")

    # Вычисляем общую сумму корреляций
    total_correlation = sum(correlations.values())

    if total_correlation == 0:
        # Если все корреляции нулевые, равномерное распределение
        num = len(pigment_spectra)
        return {pigment_id: round(100.0 / num, 2) for pigment_id in correlations.keys()}

    # Распределяем проценты пропорционально корреляциям
    percentages = {}
    remaining = 100.0

    pigment_ids = list(correlations.keys())
    for i, pigment_id in enumerate(pigment_ids[:-1]):
        percent = (correlations[pigment_id] / total_correlation) * 100.0
        # Ограничиваем минимумом 5%
        percent = max(5.0, min(percent, remaining - (len(pigment_ids) - i - 1) * 5.0))
        percentages[pigment_id] = round(percent, 2)
        remaining -= percent

    # Последний пигмент получает остаток
    if pigment_ids:
        percentages[pigment_ids[-1]] = round(max(5.0, remaining), 2)

    # Нормализуем до 100%
    total = sum(percentages.values())
    if total != 100.0:
        diff = 100.0 - total
        if pigment_ids:
            percentages[pigment_ids[-1]] = round(percentages.get(pigment_ids[-1], 0) + diff, 2)

    return percentages


def calculate_analysis_result(analysis_id, pigment_ids, spectrum_str, pigments_data):
    """
    Выполняет расчет процентов пигментов для заявки на основе сравнения спектров.
    Имитация долгой операции с задержкой 5-10 секунд.

    Args:
        analysis_id: ID заявки на спектральный анализ
        pigment_ids: Список ID пигментов в заявке
        spectrum_str: Строка спектра заявки в формате "400,25;450,65;500,45;..."
        pigments_data: Список словарей {"id": int, "spectrum": str} со спектрами пигментов

    Returns:
        dict: Результат расчета с ID заявки и процентами пигментов
    """
    if not pigment_ids:
        print(f"[Async Service] Нет пигментов для заявки {analysis_id}")
        return {
            "analysis_id": analysis_id,
            "pigments": [],
            "accuracy": 0.0,
        }

    # Задержка 5-10 секунд (случайная для реалистичности)
    delay = random.uniform(5, 10)
    time.sleep(delay)

    # Парсим спектр заявки
    analysis_spectrum = parse_spectrum(spectrum_str)

    if not analysis_spectrum:
        print(f"[Async Service] Спектр заявки не найден или пуст для заявки {analysis_id}, используем равномерное распределение")
        # Если спектра нет, равномерное распределение
        num_pigments = len(pigment_ids)
        percentages = {pigment_id: round(100.0 / num_pigments, 2) for pigment_id in pigment_ids}
        # Корректируем последний элемент для точности
        total = sum(percentages.values())
        if total != 100.0:
            last_id = pigment_ids[-1]
            percentages[last_id] = round(percentages[last_id] + (100.0 - total), 2)
    else:
        print(f"[Async Service] ✅ Получен спектр заявки с {len(analysis_spectrum)} точками для заявки {analysis_id}")
        print(f"[Async Service] 📦 Количество пигментов с данными: {len(pigments_data)}")

        # Рассчитываем проценты на основе сравнения спектров
        print(f"[Async Service] 🔬 Вычисляю корреляции спектров...")
        percentages = calculate_pigment_percentages_from_spectrum(analysis_spectrum, pigments_data)
        print(f"[Async Service] ✅ Корреляции вычислены, проценты: {percentages}")

        # Если не все пигменты получили проценты, распределяем остаток
        for pigment_id in pigment_ids:
            if pigment_id not in percentages:
                percentages[pigment_id] = 0.0

    # Формируем результат с привязкой к pigment_id
    pigments_result = []
    for pigment_id in pigment_ids:
        pigments_result.append({
            "pigment_id": pigment_id,
            "percent": percentages.get(pigment_id, 0.0),
        })

    # Вычисляем точность на основе качества спектров
    if analysis_spectrum:
        # Точность зависит от количества точек спектра и наличия спектров пигментов
        base_accuracy = 80.0
        spectrum_points_bonus = len(analysis_spectrum) * 1.0
        pigments_with_spectra = sum(1 for p in pigments_data if p.get("spectrum"))
        pigments_bonus = pigments_with_spectra * 2.0
        accuracy = min(95.0, base_accuracy + spectrum_points_bonus + pigments_bonus)
    else:
        accuracy = 75.0  # Низкая точность без спектра

    print(f"[Async Service] 📈 ИТОГОВЫЕ РЕЗУЛЬТАТЫ:")
    print(f"[Async Service]   - Проценты: {percentages}")
    print(f"[Async Service]   - Точность анализа: {accuracy}%")

    return {
        "analysis_id": analysis_id,
        "pigments": pigments_result,
        "accuracy": round(accuracy, 2),
    }


def result_callback(task):
    """
    Колбэк для отправки результатов в основной сервис после завершения расчета.

    Args:
        task: Future объект с результатом выполнения calculate_analysis_result
    """
    try:
        result = task.result()
        print("=" * 80)
        print(f"[Async Service] ✅ РАСЧЕТ ЗАВЕРШЕН для заявки {result['analysis_id']}")
        print(f"[Async Service] Результаты:")
        print(f"[Async Service]   - Проценты: {result.get('pigments', [])}")
        print(f"[Async Service]   - Точность: {result.get('accuracy', 0)}%")
        print("=" * 80)
    except futures._base.CancelledError:
        print("[Async Service] Задача была отменена")
        return
    except Exception as e:
        print(f"[Async Service] Ошибка при выполнении задачи: {e}")
        return

    # Отправляем результаты в основной сервис
    analysis_id = result["analysis_id"]
    url = f"{MAIN_SERVICE_URL}/{analysis_id}/update-results"

    # Формируем данные для отправки
    payload = {
        "pigments": result["pigments"],
        "accuracy": result["accuracy"],
    }

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            print(f"[Async Service] Результаты успешно отправлены в основной сервис для заявки {analysis_id}")
        else:
            print(f"[Async Service] Ошибка при отправке результатов: {response.status_code} - {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"[Async Service] Ошибка HTTP запроса: {e}")


@api_view(['POST'])
def process_analysis(request):
    """
    Обработчик POST-запроса для запуска асинхронной обработки заявки.

    Принимает JSON:
    {
        "analysis_id": "uuid-заявки",
        "pigment_ids": [1, 2, 3],
        "spectrum": "400,25;450,65;500,45;...",
        "pigments": [
            {"id": 1, "spectrum": "400,30;450,70;500,50;..."},
            {"id": 2, "spectrum": "400,20;450,60;500,40;..."}
        ]
    }

    Возвращает 200 OK сразу, обработка происходит в фоне.
    """
    if "analysis_id" not in request.data:
        return Response(
            {"error": "Не указан analysis_id"},
            status=status.HTTP_400_BAD_REQUEST
        )

    analysis_id = request.data["analysis_id"]
    pigment_ids = request.data.get("pigment_ids", [])
    spectrum_str = request.data.get("spectrum", "")
    pigments_data = request.data.get("pigments", [])  # Список пигментов со спектрами

    print("=" * 80)
    print(f"[Async Service] ⚡ ПОЛУЧЕН ЗАПРОС НА ОБРАБОТКУ")
    print(f"[Async Service] Analysis ID: {analysis_id}")
    print(f"[Async Service] Количество пигментов: {len(pigment_ids)}")
    print(f"[Async Service] ID пигментов: {pigment_ids}")
    print(f"[Async Service] Спектр заявки: {spectrum_str}")
    print(f"[Async Service] Данные пигментов: {len(pigments_data)} элементов")

    for i, p in enumerate(pigments_data):
        pigment_id = p.get("id", "unknown")
        pigment_spectrum = p.get("spectrum", "")
        if pigment_spectrum:
            print(f"[Async Service] Пигмент {i+1} (id={pigment_id}): spectrum={pigment_spectrum[:60]}...")
        else:
            print(f"[Async Service] Пигмент {i+1} (id={pigment_id}): spectrum=НЕТ")

    pigments_with_spectra = sum(1 for p in pigments_data if p.get("spectrum"))
    print(f"[Async Service] Пигментов со спектрами: {pigments_with_spectra} из {len(pigments_data)}")
    print("=" * 80)

    # Запускаем задачу в фоновом режиме
    task = executor.submit(calculate_analysis_result, analysis_id, pigment_ids, spectrum_str, pigments_data)
    task.add_done_callback(result_callback)

    print(f"[Async Service] ✅ Задача обработки запущена в фоне для заявки {analysis_id}")

    # Возвращаем ответ сразу, не дожидаясь завершения расчета
    return Response(
        {
            "status": "ok",
            "message": f"Обработка заявки {analysis_id} запущена",
        },
        status=status.HTTP_200_OK
    )

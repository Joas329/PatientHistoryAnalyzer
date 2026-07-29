from datetime import datetime

def bubble_sort_medical_records(records):
    n = len(records)

    for i in range(n):
        for j in range(0, n - i - 1):
            date1 = datetime.strptime(records[j].fecha_toma_muestra, "%d/%m/%Y %H:%M:%S")
            date2 = datetime.strptime(records[j + 1].fecha_toma_muestra, "%d/%m/%Y %H:%M:%S")

            if date1 > date2:
                records[j], records[j + 1] = records[j + 1], records[j]

    return records
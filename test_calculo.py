import math
# --- AQUÍ PEGAS TU FUNCIÓN ---
def calcular_monto(tipo, minutos):
    if minutos <= 0: return 0
    minutos = minutos + 3  # Tu ajuste
    
    if tipo == 'MOTO':
        if minutos <= 30: return 2
        elif minutos <= 60: return 3
        elif minutos <= 80: return 4
        elif minutos <= 100: return 5
        elif minutos <= 120: return 6
        else: return 6 + math.ceil((minutos - 120) / 20)
    elif tipo == 'AUTO':
        if minutos <= 25: return 3
        elif minutos <= 40: return 4
        elif minutos <= 60: return 5
        minutos_restantes = minutos - 60
        horas_completas = minutos_restantes // 60
        minutos_en_hora_actual = minutos_restantes % 60
        monto = 5 + (horas_completas * 5)
        if minutos_en_hora_actual > 0:
            if minutos_en_hora_actual <= 10:   monto += 1
            elif minutos_en_hora_actual <= 30: monto += 2
            elif minutos_en_hora_actual <= 40: monto += 3
            elif minutos_en_hora_actual <= 50: monto += 4
            else: monto += 5
        return monto
    return 0

# --- ZONA DE PRUEBAS ---
print("--- PRUEBA DE COBRO ---")
# Probamos un AUTO que estuvo 57 minutos (debería cobrar como 60 -> 5 Bs)
print(f"Auto (57 min reales): {calcular_monto('AUTO', 119)} Bs")

# Probamos una MOTO que estuvo 27 minutos (debería cobrar como 30 -> 2 Bs)
print(f"Moto (27 min reales): {calcular_monto('MOTO', 27)} Bs")

# Probamos un AUTO que estuvo 61 minutos (debería cobrar como 64 -> 6 Bs)
print(f"Auto (61 min reales): {calcular_monto('AUTO', 61)} Bs")
from flask import Flask, render_template, request, url_for, redirect, session, jsonify, flash, Response
import sqlite3
import os
import csv
import io
from datetime import datetime, timedelta  # <--- Consolidado aquí
import math
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import jsonify, request

app = Flask(__name__)

# --- CONFIGURACIÓN DE SEGURIDAD CONSOLIDADA ---
app.config['SECRET_KEY'] = 'parqueo_seguro_pro_123_villa_dolores' 
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365) # La sesión dura un año
@app.before_request
def hacer_sesion_permanente():
    session.permanent = True
# --- CONFIGURACIÓN DE BASE DE DATOS ---
def conectar_db():
    conn = sqlite3.connect('parqueo.db')
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_db():
    with conectar_db() as conn:
        # 1. Tabla de Tickets
        conn.execute('''CREATE TABLE IF NOT EXISTS tickets 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      placa TEXT, 
                      tipo TEXT, 
                      fecha_entrada DATETIME, 
                      fecha_salida DATETIME, 
                      monto_pagado REAL DEFAULT 0, 
                      estado TEXT DEFAULT 'ACTIVO',
                      usuario_registro TEXT,
                      usuario_cobro TEXT)''')
        
        # 2. Tabla de Usuarios
        conn.execute('''CREATE TABLE IF NOT EXISTS usuarios 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      username TEXT UNIQUE, 
                      password TEXT, 
                      rol TEXT DEFAULT 'empleado')''')
        
        # 3. NUEVO: Tabla de Configuración (Para guardar la Clave Maestra)
        conn.execute('''CREATE TABLE IF NOT EXISTS configuracion 
                       (id INTEGER PRIMARY KEY, 
                        clave_maestra TEXT)''')
        
        # Insertar clave maestra por defecto solo si la tabla está vacía
        conf = conn.execute("SELECT * FROM configuracion").fetchone()
        if not conf:
            conn.execute("INSERT INTO configuracion (id, clave_maestra) VALUES (1, 'VILLA2026')")
            
        conn.commit()

# --- MIGRACIÓN AUTOMÁTICA ---
# Esto añade la columna usuario_cobro si no existe en una base de datos vieja
def migrar_db():
    try:
        with conectar_db() as conn:
            conn.execute("ALTER TABLE tickets ADD COLUMN usuario_cobro TEXT")
            conn.commit()
    except:
        pass # La columna ya existe

inicializar_db()
migrar_db()

# --- DECORADOR DE SEGURIDAD ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

 
def obtener_config_maestra():
    try:
        with conectar_db() as conn:
            # Seleccionamos la columna exacta: clave_maestra
            res = conn.execute("SELECT clave_maestra FROM configuracion LIMIT 1").fetchone()
            if res:
                return res['clave_maestra']
            return "1234"  # Clave de respaldo si la tabla está vacía
    except Exception as e:
        print(f"Error al obtener clave: {e}")
        return "1234"
    
# --- LÓGICA DE COBRO (VILLA DOLORES) ---
def calcular_monto(tipo, fecha_ent_str, fecha_sal_obj):
    # Convertir la fecha de entrada de texto a objeto de tiempo
    inicio = datetime.strptime(fecha_ent_str, '%Y-%m-%d %H:%M:%S')
    fin = fecha_sal_obj

    es_nocturno = "_N" in tipo
    tipo_base = tipo.replace("_N", "") # Limpiamos el tipo para MOTO o AUTO

    minutos_a_cobrar = 0
    monto_base = 0

    if es_nocturno:
        monto_base = 10 # Base fija por la noche
        
        # Definir los límites de la noche (20:00 a 08:00)
        if inicio.hour >= 20:
            # Entró en la noche (ej. 21:00)
            inicio_noche = inicio.replace(hour=20, minute=0, second=0, microsecond=0)
            fin_noche = (inicio + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
        elif inicio.hour < 8:
            # Entró en la madrugada (ej. 02:00 AM)
            inicio_noche = (inicio - timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
            fin_noche = inicio.replace(hour=8, minute=0, second=0, microsecond=0)
        else:
            # Entró de día (ej. 16:00)
            inicio_noche = inicio.replace(hour=20, minute=0, second=0, microsecond=0)
            fin_noche = (inicio + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)

        minutos_tarde = 0
        minutos_manana = 0

        # Calcular tiempo consumido ANTES de las 20:00
        if inicio < inicio_noche:
            limite_tarde = min(fin, inicio_noche)
            minutos_tarde = max(0, (limite_tarde - inicio).total_seconds() / 60)
        
        # Calcular tiempo consumido DESPUÉS de las 08:00 AM
        if fin > fin_noche:
            inicio_manana = max(inicio, fin_noche)
            minutos_manana = max(0, (fin - inicio_manana).total_seconds() / 60)

        # Unimos las horas del día ignorando el bloque nocturno
        minutos_a_cobrar = math.ceil(minutos_tarde + minutos_manana)

    else:
        # Si NO es nocturno, cuenta todos los minutos transcurridos normalmente
        minutos_a_cobrar = math.ceil((fin - inicio).total_seconds() / 60)

    # Si fue marcado nocturno y no consumió tiempo de día, solo paga 10 Bs.
    if minutos_a_cobrar <= 0 and es_nocturno:
        return monto_base
    elif minutos_a_cobrar <= 0:
        return 0

    # Aplicamos tu lógica original de cobro con los 3 minutos de tolerancia
    minutos = minutos_a_cobrar + 3
    monto_extra = 0

    if tipo_base == 'MOTO':
        if minutos <= 30: monto_extra = 2
        elif minutos <= 60: monto_extra = 3
        elif minutos <= 80: monto_extra = 4
        elif minutos <= 100: monto_extra = 5
        elif minutos <= 120: monto_extra = 6
        else: monto_extra = 6 + math.ceil((minutos - 120) / 20)
        
    elif tipo_base == 'AUTO':
        if minutos <= 25: monto_extra = 3
        elif minutos <= 40: monto_extra = 4
        elif minutos <= 60: monto_extra = 5
        else:
            minutos_restantes = minutos - 60
            horas_completas = minutos_restantes // 60
            minutos_en_hora_actual = minutos_restantes % 60
            monto_extra = 5 + (horas_completas * 5)
            if minutos_en_hora_actual > 0:
                if minutos_en_hora_actual <= 10:   monto_extra += 1
                elif minutos_en_hora_actual <= 30: monto_extra += 2
                elif minutos_en_hora_actual <= 40: monto_extra += 3
                elif minutos_en_hora_actual <= 50: monto_extra += 4
                else: monto_extra += 5
                
    return monto_base + monto_extra

# --- RUTAS ---
@app.route('/setup', methods=['GET', 'POST'])
def setup():
    with conectar_db() as conn:
        # Si ya existe algún usuario en la BD, bloqueamos esta ruta y mandamos al login
        total = conn.execute("SELECT COUNT(*) as c FROM usuarios").fetchone()['c']
        if total > 0:
            return redirect(url_for('login'))

    if request.method == 'POST':
        u = request.form.get('username').lower().strip()
        p = request.form.get('password')
        mk = request.form.get('master_key')

        if u and p and mk:
            hashed_pw = generate_password_hash(p)
            with conectar_db() as conn:
                # Creamos el administrador principal
                conn.execute("INSERT INTO usuarios (username, password, rol) VALUES (?, ?, ?)", (u, hashed_pw, 'admin'))
                # Guardamos su clave maestra
                conn.execute("UPDATE configuracion SET clave_maestra = ? WHERE id = 1", (mk,))
                conn.commit()
            return redirect(url_for('login'))
        else:
            return render_template('setup.html', error="Todos los campos son obligatorios")
            
    return render_template('setup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # NUEVO: Verificamos si no hay usuarios para mandarlo a la instalación
    with conectar_db() as conn:
        total_usuarios = conn.execute("SELECT COUNT(*) as c FROM usuarios").fetchone()['c']
        if total_usuarios == 0:
            return redirect(url_for('setup'))

    if request.method == 'POST':
        user_input = request.form.get('usuario').lower().strip()
        pass_input = request.form.get('password')
        with conectar_db() as conn:
            user = conn.execute("SELECT * FROM usuarios WHERE username = ?", (user_input,)).fetchone()
            if user and check_password_hash(user['password'], pass_input):
                session['usuario'] = user['username']
                session['rol'] = user['rol']
                return redirect(url_for('index'))
        return render_template('login.html', error="Credenciales incorrectas")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    ticket_entrada = session.pop('ticket_entrada', None)
    ticket_salida = session.pop('ticket_salida', None)
    error = session.pop('error', None)
    # NUEVO: Capturar mensajes de éxito
    exito = session.pop('exito', None)

    with conectar_db() as conn:
        reporte_dias = conn.execute("""
            SELECT DATE(fecha_salida) as dia, SUM(monto_pagado) as total 
            FROM tickets WHERE estado='PAGADO' 
            GROUP BY dia ORDER BY dia DESC LIMIT 7
        """).fetchall()

        ultimos_movimientos = conn.execute("""
            SELECT id, placa, tipo, 
            strftime('%H:%M', fecha_entrada) as hora_e, 
            strftime('%H:%M', fecha_salida) as hora_s, 
            monto_pagado, estado, usuario_registro, usuario_cobro
            FROM tickets ORDER BY id DESC 
        """).fetchall()
        
        # NUEVO: Obtenemos la clave maestra de la BD
        config = conn.execute("SELECT clave_maestra FROM configuracion WHERE id = 1").fetchone()
        clave_maestra_db = config['clave_maestra'] if config else 'VILLA2026'

    return render_template('index.html', 
                           ticket_entrada=ticket_entrada, 
                           ticket_salida=ticket_salida, 
                           error=error,
                           exito=exito,
                           ingresos_dias=reporte_dias,
                           ultimos_movimientos=ultimos_movimientos,
                           config_maestra=clave_maestra_db) # ENVIAMOS ESTA VARIABLE

@app.route('/registrar', methods=['POST'])
@login_required
def registrar():
    placa_input = request.form.get('placa', '').upper().strip()
    tipo = request.form.get('tipo', 'AUTO')
    ahora = datetime.now()
    fecha_ent_db = ahora.strftime('%Y-%m-%d %H:%M:%S')
    
    # Si el usuario no escribe placa, la dejamos totalmente vacía
    placa_final = placa_input if placa_input else ""
    
    with conectar_db() as conn:
        cursor = conn.cursor()
        # Aquí insertamos placa_final en lugar de "TEMP"
        cursor.execute("""INSERT INTO tickets 
                       (placa, tipo, fecha_entrada, estado, usuario_registro) 
                       VALUES (?, ?, ?, ?, ?)""",
                       (placa_final, tipo, fecha_ent_db, 'ACTIVO', session['usuario']))
        ticket_id = cursor.lastrowid

    session['ticket_entrada'] = {
        'id': ticket_id, 'placa': placa_final, 'tipo': tipo,
        'fecha': ahora.strftime('%d/%m/%Y'), 'hora': ahora.strftime('%H:%M:%S')
    }
    return redirect(url_for('index'))

@app.route('/buscar_placa')
@login_required
def buscar_placa():
    query = request.args.get('q', '').upper()
    if len(query) < 1: return jsonify([]) # Buscamos incluso si escribe una sola letra/número
    
    with conectar_db() as conn:
        # Buscamos por Placa O por ID (convertimos ID a texto para comparar)
        rows = conn.execute("""
            SELECT id, placa, tipo, fecha_entrada 
            FROM tickets 
            WHERE (placa LIKE ? OR CAST(id AS TEXT) LIKE ?) 
            AND estado = 'ACTIVO' 
            LIMIT 5
        """, (f"%{query}%", f"{query}%")).fetchall()
        
        resultados = []
        ahora = datetime.now()
        
        for row in rows:
            # Calcular tiempo total para mostrar en pantalla
            entrada = datetime.strptime(row['fecha_entrada'], '%Y-%m-%d %H:%M:%S')
            minutos_totales = math.ceil((ahora - entrada).total_seconds() / 60)
            
            # El cálculo monetario usa nuestra nueva función
            monto = calcular_monto(row['tipo'], row['fecha_entrada'], ahora)
            
            resultados.append({
                "id": row['id'],
                "placa": row['placa'] if row['placa'] else "S/P",
                "tiempo": minutos_totales,
                "monto": monto
            })
            
    return jsonify(resultados)

@app.route('/salida_unificada', methods=['POST'])
@login_required
def salida_unificada():
    dato = request.form['codigo_qr'].upper().strip()
    ahora = datetime.now()
    
    with conectar_db() as conn:
        t = conn.execute("""
            SELECT * FROM tickets 
            WHERE (id = ? OR placa = ?) 
            AND estado = 'ACTIVO'
        """, (dato, dato)).fetchone()

        if t:
            # Calcular tiempo total para guardar en la base de datos
            entrada = datetime.strptime(t['fecha_entrada'], '%Y-%m-%d %H:%M:%S')
            minutos_totales = math.ceil((ahora - entrada).total_seconds() / 60)
            
            # El cálculo monetario usa nuestra nueva función
            cobro = calcular_monto(t['tipo'], t['fecha_entrada'], ahora)
            
            # GUARDAMOS QUIÉN COBRÓ
            conn.execute("""UPDATE tickets SET 
                         fecha_salida=?, monto_pagado=?, estado='PAGADO', usuario_cobro=? 
                         WHERE id=?""",
                         (ahora.strftime('%Y-%m-%d %H:%M:%S'), cobro, session['usuario'], t['id']))
            conn.commit()

            session['ticket_salida'] = {'placa': t['placa'], 'monto': cobro, 'tiempo': minutos_totales}
        else:
            session['error'] = "Vehículo no encontrado o ya pagado."
            
    return redirect(url_for('index'))

@app.route('/admin/exportar')
@login_required
def exportar_datos():
    if session.get('rol') != 'admin': return "Acceso denegado", 403

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';') # Delimitador para Excel Latino

    with conectar_db() as conn:
        cursor = conn.execute("SELECT * FROM tickets")
        columnas = [desc[0] for desc in cursor.description]
        writer.writerow(columnas)
        for fila in cursor.fetchall():
            writer.writerow(list(fila))
    
    return Response(
        output.getvalue().encode('utf-8-sig'), # UTF-8-SIG para acentos en Excel
        mimetype="text/csv", 
        headers={"Content-Disposition": "attachment;filename=reporte_parqueo.csv"}
    )

@app.route('/admin/reset_tickets', methods=['POST'])
@login_required
def reset_tickets():
    if session.get('rol') == 'admin':
        with conectar_db() as conn:
            conn.execute("DELETE FROM tickets")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='tickets'")
            conn.commit()
    return redirect(url_for('index'))

@app.route('/anular/<int:id>', methods=['POST'])
@login_required
def anular_registro(id):
    with conectar_db() as conn:
        conn.execute("UPDATE tickets SET estado = 'ANULADO' WHERE id = ?", (id,))
        conn.commit()
    return redirect(url_for('index'))

@app.context_processor
def utilidad_reporte():
    hoy = datetime.now().strftime('%Y-%m-%d')
    with conectar_db() as conn:
        res = conn.execute("SELECT SUM(monto_pagado) as total FROM tickets WHERE fecha_salida LIKE ?", (f"{hoy}%",)).fetchone()
        cont = conn.execute("SELECT COUNT(*) as cant FROM tickets WHERE estado='ACTIVO'").fetchone()
    return dict(total_caja=res['total'] or 0, en_parqueo=cont['cant'])

@app.route('/admin/usuarios')
@login_required
def gestion_usuarios():
    if session.get('rol') != 'admin': return redirect(url_for('index'))
    with conectar_db() as conn:
        users = conn.execute("SELECT id, username, rol FROM usuarios").fetchall()
    return render_template('usuarios.html', usuarios=users)

@app.route('/admin/usuarios/crear', methods=['POST'])
@login_required
def crear_usuario():
    if session.get('rol') != 'admin': return redirect(url_for('index'))
    u = request.form.get('username').lower().strip()
    p = request.form.get('password')
    r = request.form.get('rol')
    if u and p:
        h = generate_password_hash(p)
        try:
            with conectar_db() as conn:
                conn.execute("INSERT INTO usuarios (username, password, rol) VALUES (?, ?, ?)", (u, h, r))
                conn.commit()
        except: pass
    return redirect(url_for('gestion_usuarios'))

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response



# --- RUTA PARA ELIMINAR UN USUARIO ---
@app.route('/admin/usuarios/eliminar/<int:id>', methods=['POST'])
@login_required
def eliminar_usuario(id):
    if session.get('rol') != 'admin':
        return redirect(url_for('index'))
    
    with conectar_db() as conn:
        # Obtenemos el nombre del usuario antes de borrarlo para verificar
        user = conn.execute("SELECT username FROM usuarios WHERE id = ?", (id,)).fetchone()
        
        # Evitar que el admin se borre a sí mismo
        if user and user['username'] == session['usuario']:
            # Podrías pasar un mensaje de error aquí
            return redirect(url_for('gestion_usuarios'))
            
        conn.execute("DELETE FROM usuarios WHERE id = ?", (id,))
        conn.commit()
        
    return redirect(url_for('gestion_usuarios'))

# --- RUTAS DE REIMPRESIÓN ---

@app.route('/reimprimir_ultimo')
@login_required
def reimprimir_ultimo():
    with conectar_db() as conn:
        # Obtenemos el último registro insertado
        t = conn.execute("SELECT * FROM tickets ORDER BY id DESC LIMIT 1").fetchone()
        
        if t:
            # Convertimos la fecha de la DB a objeto datetime para formatear hora y fecha
            f_ent = datetime.strptime(t['fecha_entrada'], '%Y-%m-%d %H:%M:%S')
            
            # Cargamos la sesión igual que en la ruta /registrar
            session['ticket_entrada'] = {
                'id': t['id'], 
                'placa': t['placa'], 
                'tipo': t['tipo'],
                'fecha': f_ent.strftime('%d/%m/%Y'), 
                'hora': f_ent.strftime('%H:%M')
            }
        else:
            session['error'] = "No hay tickets para reimprimir."
            
    return redirect(url_for('index'))

@app.route('/reimprimir/<int:id>')
@login_required
def reimprimir_especifico(id):
    with conectar_db() as conn:
        t = conn.execute("SELECT * FROM tickets WHERE id = ?", (id,)).fetchone()
        
        if t:
            f_ent = datetime.strptime(t['fecha_entrada'], '%Y-%m-%d %H:%M:%S')
            
            # Si el ticket aún está ACTIVO, imprimimos el ticket de entrada
            if t['estado'] == 'ACTIVO'or 'PAGADO':
                session['ticket_entrada'] = {
                    'id': t['id'], 
                    'placa': t['placa'], 
                    'tipo': t['tipo'],
                    'fecha': f_ent.strftime('%d/%m/%Y'), 
                    'hora': f_ent.strftime('%H:%M')
                }
            # Si ya está PAGADO, imprimimos el recibo de salida
            elif t['estado'] == 'PAGADO':
                f_sal = datetime.strptime(t['fecha_salida'], '%Y-%m-%d %H:%M:%S')
                session['ticket_salida_print'] = {
                    'id': t['id'],
                    'placa': t['placa'],
                    'entrada': f_ent.strftime('%d/%m/%Y %H:%M'),
                    'salida': f_sal.strftime('%d/%m/%Y %H:%M'),
                    'monto': t['monto_pagado'],
                    'cajero': t['usuario_cobro'] or t['usuario_registro']
                }
        else:
            session['error'] = "Ticket no encontrado."
            
    return redirect(url_for('index'))   

@app.route('/admin/cambiar_maestra', methods=['POST'])
@login_required
def cambiar_maestra():
    if session.get('rol') != 'admin':
        return "No autorizado", 403
        
    pass_admin = request.form.get('pass_admin')
    nueva_clave = request.form.get('nueva_clave')
    
    with conectar_db() as conn:
        # Verificamos la contraseña del administrador logueado
        user = conn.execute("SELECT password FROM usuarios WHERE username = ?", (session['usuario'],)).fetchone()
        
        if user and check_password_hash(user['password'], pass_admin):
            if nueva_clave:
                conn.execute("UPDATE configuracion SET clave_maestra = ? WHERE id = 1", (nueva_clave,))
                conn.commit()
                session['exito'] = "Clave Maestra actualizada correctamente."
        else:
            session['error'] = "Contraseña de administrador incorrecta. Cambio cancelado."
            
    return redirect(url_for('index'))



@app.before_request
def manejar_sesion():
    # Esto hace que el tiempo de expiración se cuente desde el último clic
    session.modified = True

@app.route('/eliminar_vehiculo/<int:id>', methods=['POST'])
@login_required
def eliminar_vehiculo(id):
    clave_ingresada = request.form.get('clave_maestra')
    clave_real = obtener_config_maestra()

    if clave_ingresada == clave_real:
        try:
            with conectar_db() as conn:
                # Usamos tu columna 'estado' y 'id'
                resultado = conn.execute("DELETE FROM tickets WHERE id = ? AND estado = 'ACTIVO'", (id,))
                conn.commit()
                
                if resultado.rowcount > 0:
                    flash("Vehículo eliminado correctamente.", "exito")
                else:
                    flash("No se pudo eliminar: el vehículo ya fue cobrado o no existe.", "error")
        except Exception as e:
            flash(f"Error en la base de datos: {str(e)}", "error")
    else:
        flash("Contraseña Maestra incorrecta.", "error")

    return redirect(url_for('index'))
    
@app.route('/marcar_nocturno/<int:id>', methods=['POST'])
@login_required
def marcar_nocturno(id):
    with conectar_db() as conn:
        t = conn.execute("SELECT tipo FROM tickets WHERE id = ?", (id,)).fetchone()
        if t and not t['tipo'].endswith('_N'):
            nuevo_tipo = t['tipo'] + "_N"
            conn.execute("UPDATE tickets SET tipo = ? WHERE id = ?", (nuevo_tipo, id))
            conn.commit()
            flash("Vehículo marcado con Tarifa Nocturna.", "exito")
    return redirect(url_for('index'))

@app.route('/editar_placa', methods=['POST'])
@login_required
def editar_placa():
    id_ticket = request.form.get('id_ticket')
    nueva_placa = request.form.get('nueva_placa', '').upper().strip()
    
    try:
        with conectar_db() as conn:
            conn.execute("UPDATE tickets SET placa = ? WHERE id = ?", (nueva_placa, id_ticket))
            conn.commit()
        # Esto es lo que JavaScript necesita recibir:
        return {"status": "success", "id": id_ticket}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
    
@app.route('/editar_tipo', methods=['POST'])
@login_required
def editar_tipo():
    id_ticket = request.form.get('id_ticket')
    nuevo_tipo_base = request.form.get('nuevo_tipo', '').upper().strip()
    
    # Solo permitimos estas dos opciones base
    if nuevo_tipo_base not in ['AUTO', 'MOTO']:
        return jsonify({"status": "error", "message": "Solo se permite AUTO o MOTO"}), 400

    try:
        with conectar_db() as conn:
            # Primero revisamos si el ticket actual es nocturno
            t = conn.execute("SELECT tipo FROM tickets WHERE id = ?", (id_ticket,)).fetchone()
            if t:
                # Si el tipo actual tiene "_N", mantenemos el sufijo en el nuevo tipo
                es_nocturno = "_N" in t['tipo']
                tipo_final = nuevo_tipo_base + "_N" if es_nocturno else nuevo_tipo_base
                
                conn.execute("UPDATE tickets SET tipo = ? WHERE id = ?", (tipo_final, id_ticket))
                conn.commit()
                return jsonify({"status": "success"})
            return jsonify({"status": "error", "message": "Ticket no encontrado"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500    

@app.route('/revertir_cobro/<int:id>', methods=['POST'])
@login_required
def revertir_cobro(id):
    clave_ingresada = request.form.get('clave_maestra')
    clave_real = obtener_config_maestra() # Usamos tu función de seguridad existente

    if clave_ingresada == clave_real:
        try:
            with conectar_db() as conn:
                # 1. Verificamos que el ticket realmente esté PAGADO
                t = conn.execute("SELECT estado FROM tickets WHERE id = ?", (id,)).fetchone()
                
                if t and t['estado'] == 'PAGADO':
                    # 2. Lo devolvemos a estado ACTIVO y limpiamos los datos de cobro
                    conn.execute("""UPDATE tickets SET 
                                 estado = 'ACTIVO', 
                                 fecha_salida = NULL, 
                                 monto_pagado = 0,
                                 usuario_cobro = NULL 
                                 WHERE id = ?""", (id,))
                    conn.commit()
                    flash("El cobro ha sido anulado. El vehículo está activo nuevamente.", "exito")
                else:
                    flash("No se puede revertir: el registro no existe o ya está activo.", "error")
        except Exception as e:
            flash(f"Error en la base de datos: {str(e)}", "error")
    else:
        flash("Contraseña Maestra incorrecta.", "error")

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
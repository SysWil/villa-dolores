from app import app, db, Usuario # Asegúrate de que estos nombres coincidan con tu código

with app.app_context():
    # Creamos al dueño (Admin)
    dueño = Usuario(
        usuario="admin", 
        password="TuPasswordSeguro", # Aquí pon la clave que el dueño quiera
        rol="admin"
    )
    db.session.add(dueño)
    db.session.commit()
    print("Dueño creado exitosamente. Ya puedes borrar este archivo.")
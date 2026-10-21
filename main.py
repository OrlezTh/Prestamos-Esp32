from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Prestamo(BaseModel):
    nombre: str
    apellido: str
    prestado: int
    cantidad_cuotas: int
    cuota_monto: int

@app.get("/prestamos")
def obtener_prestamos():
    if not os.path.exists("datos_cargados.json"):
        return []
    try:
        with open("datos_cargados.json", "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
            return datos if isinstance(datos, list) else [datos]
    except Exception:
        return []

@app.post("/prestamos")
def crear_prestamo(prestamo: Prestamo):
    total_cuota = prestamo.cantidad_cuotas * prestamo.cuota_monto
    
    cuota_nro = [
        (f"Cuota: {i} Total: {prestamo.cuota_monto} Pagado: False",) 
        for i in range(1, prestamo.cantidad_cuotas + 1)
    ]

    nuevo_registro = {
        "Nombre": prestamo.nombre,
        "Apellido": prestamo.apellido,
        "Prestado": prestamo.prestado,
        "IDcuota": 1,
        "Cantidad_cuotas": prestamo.cantidad_cuotas,
        "Monto_total": total_cuota,
        "Cuota_monto": prestamo.cuota_monto,
        "Cuotas": cuota_nro
    }

    try:
        if os.path.exists("datos_cargados.json"):
            with open("datos_cargados.json", "r", encoding="utf-8") as archivo:
                datos = json.load(archivo)
                if not isinstance(datos, list):
                    datos = [datos]
        else:
            datos = []
    except Exception:
        datos = []

    datos.append(nuevo_registro)

    with open("datos_cargados.json", "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, indent=4)

    return {"mensaje": "¡Registro agregado exitosamente!", "registro": nuevo_registro}

# NUEVA RUTA: Permite cambiar el estado de pago de una cuota específica al hacer clic en el tilde
@app.put("/prestamos/{prestamo_idx}/cuota/{cuota_idx}")
def actualizar_cuota(prestamo_idx: int, cuota_idx: int):
    if not os.path.exists("datos_cargados.json"):
        return {"error": "No hay datos"}
    
    with open("datos_cargados.json", "r", encoding="utf-8") as archivo:
        datos = json.load(archivo)
    
    if 0 <= prestamo_idx < len(datos):
        prestamo = datos[prestamo_idx]
        cuotas = prestamo["Cuotas"]
        if 0 <= cuota_idx < len(cuotas):
            # Obtiene el texto de la tupla (que se guarda como lista en JSON)
            texto_cuota = cuotas[cuota_idx][0] if isinstance(cuotas[cuota_idx], list) else cuotas[cuota_idx]
            
            # Alterna el estado de pago
            if "Pagado: False" in texto_cuota:
                nuevo_texto = texto_cuota.replace("Pagado: False", "Pagado: True")
            else:
                nuevo_texto = texto_cuota.replace("Pagado: True", "Pagado: False")
            
            cuotas[cuota_idx] = [nuevo_texto]
            
            with open("datos_cargados.json", "w", encoding="utf-8") as archivo:
                json.dump(datos, archivo, indent=4)
                
            return {"mensaje": "Estado de cuota actualizado"}
            
    return {"error": "No se encontró el registro"}
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import json
import os
import re
import uuid

# iniciar: python -m uvicorn main:app --reload

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVO = os.path.join(BASE_DIR, "datos_cargados.json")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Modelos ----------

class Prestamo(BaseModel):
    nombre: str
    apellido: str
    prestado: int
    cantidad_cuotas: int
    cuota_monto: int
    mes_inicial: int  # 1 a 12: mes en que se cobra la primera cuota


class PrestamoEditar(BaseModel):
    nombre: str
    apellido: str
    prestado: int
    # si viene, se aplica a las cuotas que todavía no están pagas
    cuota_monto: Optional[int] = None
    # si viene, reasigna el mes de TODAS las cuotas a partir de este mes
    mes_inicial: Optional[int] = None


class CuotaNueva(BaseModel):
    monto: Optional[int] = None  # si no viene, usa Cuota_monto del deudor
    mes: Optional[int] = None    # si no viene, es el mes siguiente a la última cuota


class CuotaEditar(BaseModel):
    monto: int
    mes: Optional[int] = None


# ---------- Persistencia ----------

PATRON_VIEJO = re.compile(r"Cuota:\s*(\d+)\s+Total:\s*(\d+)\s+Pagado:\s*(True|False)")


def siguiente_mes(mes):
    """Suma 1 al mes; después de 12 vuelve a 1 (enero)."""
    return mes % 12 + 1


def mes_de_cuota(mes_inicial, i):
    """Mes de la cuota i (1 = primera) a partir del mes inicial."""
    return (mes_inicial - 1 + (i - 1)) % 12 + 1


def validar_mes(mes):
    if mes is not None and not 1 <= mes <= 12:
        raise HTTPException(status_code=400, detail="El mes tiene que ser un número de 1 a 12")


def recalcular(p):
    """Renumera cuotas y actualiza cantidad y total."""
    for i, c in enumerate(p["Cuotas"], start=1):
        c["Cuota"] = i
    p["Cantidad_cuotas"] = len(p["Cuotas"])
    p["Monto_total"] = sum(c["Total"] for c in p["Cuotas"])


def migrar(datos):
    """Pasa el formato viejo (cuotas como texto) al nuevo (objetos) y agrega ids."""
    cambio = False
    for p in datos:
        if "id" not in p:
            p["id"] = uuid.uuid4().hex
            cambio = True
        nuevas = []
        for c in p.get("Cuotas", []):
            if isinstance(c, dict):
                c.setdefault("Mes", None)
                nuevas.append(c)
                continue
            texto = c[0] if isinstance(c, list) else c
            m = PATRON_VIEJO.search(texto)
            if m:
                nuevas.append({
                    "Cuota": int(m.group(1)),
                    "Total": int(m.group(2)),
                    "Pagado": m.group(3) == "True",
                    "Mes": None,
                })
            cambio = True
        p["Cuotas"] = nuevas
        if cambio:
            recalcular(p)
    return datos, cambio


def cargar():
    if not os.path.exists(ARCHIVO):
        return []
    try:
        with open(ARCHIVO, "r", encoding="utf-8") as f:
            datos = json.load(f)
        if not isinstance(datos, list):
            datos = [datos]
    except Exception:
        return []
    datos, cambio = migrar(datos)
    if cambio:
        guardar(datos)
    return datos


def guardar(datos):
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)


def buscar(datos, prestamo_id):
    for p in datos:
        if p["id"] == prestamo_id:
            return p
    raise HTTPException(status_code=404, detail="Deudor no encontrado")


def validar_cuota(p, idx):
    if not 0 <= idx < len(p["Cuotas"]):
        raise HTTPException(status_code=404, detail="Cuota no encontrada")
    return p["Cuotas"][idx]


# ---------- Deudores ----------

@app.get("/prestamos")
def obtener_prestamos():
    return cargar()


@app.post("/prestamos")
def crear_prestamo(prestamo: Prestamo):
    if prestamo.cantidad_cuotas < 1:
        raise HTTPException(status_code=400, detail="Tiene que haber al menos 1 cuota")
    validar_mes(prestamo.mes_inicial)

    nuevo = {
        "id": uuid.uuid4().hex,
        "Nombre": prestamo.nombre.strip(),
        "Apellido": prestamo.apellido.strip(),
        "Prestado": prestamo.prestado,
        "Cuota_monto": prestamo.cuota_monto,
        "Cuotas": [
            {
                "Cuota": i,
                "Total": prestamo.cuota_monto,
                "Pagado": False,
                "Mes": mes_de_cuota(prestamo.mes_inicial, i),
            }
            for i in range(1, prestamo.cantidad_cuotas + 1)
        ],
    }
    recalcular(nuevo)

    datos = cargar()
    datos.append(nuevo)
    guardar(datos)
    return {"mensaje": "¡Registro agregado exitosamente!", "registro": nuevo}


@app.put("/prestamos/{prestamo_id}")
def editar_prestamo(prestamo_id: str, cambios: PrestamoEditar):
    validar_mes(cambios.mes_inicial)
    datos = cargar()
    p = buscar(datos, prestamo_id)
    p["Nombre"] = cambios.nombre.strip()
    p["Apellido"] = cambios.apellido.strip()
    p["Prestado"] = cambios.prestado
    if cambios.cuota_monto is not None:
        p["Cuota_monto"] = cambios.cuota_monto
        for c in p["Cuotas"]:
            if not c["Pagado"]:
                c["Total"] = cambios.cuota_monto
    if cambios.mes_inicial is not None:
        for i, c in enumerate(p["Cuotas"], start=1):
            c["Mes"] = mes_de_cuota(cambios.mes_inicial, i)
    recalcular(p)
    guardar(datos)
    return {"mensaje": "Deudor actualizado"}


@app.delete("/prestamos/{prestamo_id}")
def borrar_prestamo(prestamo_id: str):
    datos = cargar()
    p = buscar(datos, prestamo_id)
    datos.remove(p)
    guardar(datos)
    return {"mensaje": "Deudor borrado"}


# ---------- Cuotas ----------

@app.post("/prestamos/{prestamo_id}/cuotas")
def agregar_cuota(prestamo_id: str, cuota: CuotaNueva):
    validar_mes(cuota.mes)
    datos = cargar()
    p = buscar(datos, prestamo_id)
    monto = cuota.monto if cuota.monto is not None else p["Cuota_monto"]
    mes = cuota.mes
    if mes is None and p["Cuotas"] and p["Cuotas"][-1].get("Mes"):
        mes = siguiente_mes(p["Cuotas"][-1]["Mes"])
    p["Cuotas"].append({
        "Cuota": len(p["Cuotas"]) + 1,
        "Total": monto,
        "Pagado": False,
        "Mes": mes,
    })
    recalcular(p)
    guardar(datos)
    return {"mensaje": "Cuota agregada"}


@app.patch("/prestamos/{prestamo_id}/cuotas/{cuota_idx}/pago")
def alternar_pago(prestamo_id: str, cuota_idx: int):
    datos = cargar()
    p = buscar(datos, prestamo_id)
    c = validar_cuota(p, cuota_idx)
    c["Pagado"] = not c["Pagado"]
    guardar(datos)
    return {"mensaje": "Estado de cuota actualizado", "Pagado": c["Pagado"]}


@app.put("/prestamos/{prestamo_id}/cuotas/{cuota_idx}")
def editar_cuota(prestamo_id: str, cuota_idx: int, cambios: CuotaEditar):
    validar_mes(cambios.mes)
    datos = cargar()
    p = buscar(datos, prestamo_id)
    c = validar_cuota(p, cuota_idx)
    c["Total"] = cambios.monto
    if cambios.mes is not None:
        c["Mes"] = cambios.mes
    recalcular(p)
    guardar(datos)
    return {"mensaje": "Cuota actualizada"}


@app.delete("/prestamos/{prestamo_id}/cuotas/{cuota_idx}")
def borrar_cuota(prestamo_id: str, cuota_idx: int):
    datos = cargar()
    p = buscar(datos, prestamo_id)
    validar_cuota(p, cuota_idx)
    p["Cuotas"].pop(cuota_idx)
    recalcular(p)
    guardar(datos)
    return {"mensaje": "Cuota borrada"}


@app.get("/")
def home():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

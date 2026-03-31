import sqlite3
import requests
import os
import subprocess
from bs4 import BeautifulSoup
from datetime import datetime
import re

# Configuración de Telegram (Los valores se leen directamente de los Secrets en GitHub Actions)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Configuración de los productos y sitios (debes ajustar URLs, tags y clases a las webs reales que quieres raspar)
PRODUCTOS = [
    {
        "modelo": "ASUS Vivobook S16 Ryzen 9",
        "tienda": "Amazon MX",
        "url": "https://www.amazon.com.mx/ASUS-Vivobook-CargaRapida-Rconocimiento-Garantia/dp/B0FKMCBKFM/ref=sr_1_1_sspa?crid=28EAWQFXZ6ZY&dib=eyJ2IjoiMSJ9.Ryckrew1fMet5qlzRvQgHH9QmMgQQWx9AA8Y5h2yv3W5f60mVeaaO5J6VwoK1Gccdgv3rfuhzaHZoc7zuMoLNkNypC9hJ5Kb71hWBA0oZTYmy9OLtmH89t2VkMtqGzNl2YkbwD3xnT6NGTM54BgmBD3eZhqszfXZBGjSEi-ZoLzxRCNFdImO8GB7C7gjXhNzeEhQdQIPYE1q_cr8wVBqZrlHyfGvnPKjeCREGZPUkdG3iFQJTAnQo16P8GK_Ea2Yoz6Hbryi82mCgDoHIUfzxs3u7_fZO8QO6WGu8pXc60I.7Fw04evRybkBwRaa9MnnozHCf2WxvaYgfzg7es177JY&dib_tag=se&keywords=asus+vivobook+s16+ryzen+9&qid=1774803714&sprefix=ASUS+Vivobook+S16%2Caps%2C173&sr=8-1-spons&ufe=app_do%3Aamzn1.fos.e9c905c0-296e-4852-9ea7-c9f4c88300d3&sp_csd=d2lkZ2V0TmFtZT1zcF9hdGY&psc=1",
        "tag": "span",
        "clase": "a-price-whole"
    },
    {
        "modelo": "Notebook Laptop Machenike L16Air 16'' Gris 16 Gb RAM 512 Gb SSD 120 Hz 2560 Px X 1600 Px QHD Amd Radeon 680m Amd Ryzen 7 7735h Teclado En Español Windows 11 Pro Sistema Español Latino",
        "tienda": "MercadoLibre MX",
        "url": "https://www.mercadolibre.com.mx/notebook-laptop-machenike-l16air-16-gris-16-gb-ram-512-gb-ssd-120-hz-2560-px-x-1600-px-qhd-amd-radeon-680m-amd-ryzen-7-7735h-teclado-en-espanol-windows-11-pro-sistema-espanol-latino/p/MLM26851954?pdp_filters=item_id%3AMLM2712346479&matt_tool=17030900#origin=share&sid=share&wid=MLM2712346479&action=copy",
        "tag": "span",
        "clase": ".ui-pdp-price__second-line .andes-money-amount__fraction"
    }
]

def init_db():
    conn = sqlite3.connect('precios_laptops.db')
    cursor = conn.cursor()
    # Crear tabla si no existe (la fecha ya está incluida en las columnas)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS precios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            modelo TEXT,
            tienda TEXT,
            precio REAL,
            link TEXT
        )
    ''')
    conn.commit()
    return conn

def enviar_notificacion_telegram(mensaje):
    """Envía un mensaje a tu teléfono mediante la API de Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"⚠️ SIMULACIÓN DE NOTIFICACIÓN (credenciales no detectadas): {mensaje}")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Error enviando notificación: {e}")

def obtener_precio(url, tag, clase):
    # Un User-Agent es vital para que las tiendas no nos bloqueen de inmediato
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    try:
        # Usamos curl por subprocess debido a que las librerías de Python suelen ser bloqueadas
        result = subprocess.run([
            "curl", "-s", "--compressed", "-m", "15",
            "-H", f"User-Agent: {user_agent}",
            "-H", "Accept-Language: es-MX,es;q=0.9",
            url
        ], capture_output=True, text=True)
        
        if result.returncode != 0 or not result.stdout:
            print(f"Error o timeout en curl para la url {url[:50]}... Código: {result.returncode}")
            return None
        
        soup = BeautifulSoup(result.stdout, 'html.parser')
        
        # Buscamos el precio con los selectores.
        # Si 'clase' viene como un CSS selector complejo (con espacios o caracteres especiales), usamos select_one
        if ' ' in clase or '>' in clase or '.' in clase:
            elemento_precio = soup.select_one(clase)
        else:
            elemento_precio = soup.find(tag, class_=clase)
            
        if elemento_precio:
            precio_texto = elemento_precio.get_text()
            # Limpiamos todo lo que no sea dígito o punto (ej. "$,", extra espacios)
            precio_limpio = re.sub(r'[^\d.]', '', precio_texto.replace(',', ''))
            return float(precio_limpio) if precio_limpio else None
        return None
    except Exception as e:
        print(f"Error obteniendo datos de {url}: {e}")
        return None

def main():
    conn = init_db()
    cursor = conn.cursor()
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    mensajes_notificacion = []
    
    for p in PRODUCTOS:
        print(f"Consultando precio para: {p['modelo']} en {p['tienda']}...")
        precio_actual = obtener_precio(p['url'], p['tag'], p['clase'])
        
        if precio_actual is not None:
            # Buscar el último precio guardado de este producto específico
            cursor.execute('''
                SELECT precio FROM precios
                WHERE modelo = ?
                ORDER BY id DESC LIMIT 1
            ''', (p['modelo'],))
            resultado = cursor.fetchone()
            
            # Si hay un precio previo, validamos si ha bajado, subido o se mantiene
            if resultado:
                ultimo_precio = float(resultado[0])
                if precio_actual < ultimo_precio:
                    mensaje = f"📉 <b>BAJÓ DE PRECIO:</b> {p['modelo']} -> ${precio_actual:,.2f} <i>(Antes: ${ultimo_precio:,.2f})</i>\n🔗 <a href='{p['url']}'>Ver Oferta</a>"
                elif precio_actual == ultimo_precio:
                    mensaje = f"➡️ <b>Se mantiene precio de:</b> {p['modelo']} -> ${precio_actual:,.2f}\n🔗 <a href='{p['url']}'>Ver Oferta</a>"
                else:
                    mensaje = f"📈 <b>SUBIÓ DE PRECIO:</b> {p['modelo']} -> ${precio_actual:,.2f} <i>(Antes: ${ultimo_precio:,.2f})</i>\n🔗 <a href='{p['url']}'>Ver Oferta</a>"
                
                print(mensaje.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
                mensajes_notificacion.append(mensaje)
            else:
                mensaje = f"🆕 <b>Primer registro de:</b> {p['modelo']} -> ${precio_actual:,.2f}\n🔗 <a href='{p['url']}'>Ver Oferta</a>"
                print(mensaje.replace("<b>", "").replace("</b>", ""))
                mensajes_notificacion.append(mensaje)

            # Guardar el nuevo precio pase lo que pase
            cursor.execute('''
                INSERT INTO precios (fecha, modelo, tienda, precio, link)
                VALUES (?, ?, ?, ?, ?)
            ''', (fecha_actual, p['modelo'], p['tienda'], precio_actual, p['url']))
            print(f"✅ Precio almacenado: {p['modelo']} - ${precio_actual}")
        else:
            print(f"❌ No se pudo rescatar el precio de {p['modelo']}. Revisa los selectores.")
            
    conn.commit()
    conn.close()
    
    # Enviar un único mensaje con todas las notificaciones
    if mensajes_notificacion:
        mensaje_final = "\n\n".join(mensajes_notificacion)
        enviar_notificacion_telegram(mensaje_final)
        
    print("Scraping finalizado y base de datos actualizada.")

if __name__ == "__main__":
    main()
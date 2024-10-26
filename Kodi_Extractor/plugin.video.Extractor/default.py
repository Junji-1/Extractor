
#-------------------------------------------------------------------------------
# Extractor por Junji.
#
# Extractor para Kodi es un software libre: puedes redistribuirlo y/o modificarlo
# bajo los términos de la Licencia Pública General GNU, según lo publicado por
# la Free Software Foundation, ya sea la versión 3 de la Licencia, o
# (a tu opción) cualquier versión posterior.
#
# Deberías haber recibido una copia de la Licencia Pública General GNU junto
# con este programa. Si no, consulta <http://www.gnu.org/licenses/>.
#
#-------------------------------------------------------------------------------
#
# Exención de Responsabilidad
#
# Este addon solo proporciona acceso a contenido público y legal a través de
# una URL de acceso libre. El usuario es responsable del contenido al que
# accede utilizando este addon. No promovemos ni apoyamos el uso ilegal de 
# este addon.
#
# Por favor, utilice el addon de acuerdo con las leyes locales, y respete 
# los derechos de propiedad intelectual.
#-------------------------------------------------------------------------------


import sys
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urlencode, urlparse, parse_qsl

ADDON = xbmcaddon.Addon()
if len(sys.argv) > 1:
    ADDON_HANDLE = int(sys.argv[1])
else:
    ADDON_HANDLE = -1  # O cualquier otro valor por defecto que consideres seguro

BASE_URL = sys.argv[0]
SCRAPER_URL = ADDON.getSetting('scraper_url')


def is_valid_url(url):
    """Comprueba si una URL es válida."""
    parsed = urlparse(url)
    return all([parsed.scheme, parsed.netloc])


def fetch_html_content(url):
    """Obtiene el contenido HTML de una página dada."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        xbmc.log(f'Error al acceder a la página: {e}', xbmc.LOGERROR)
        return None


def extract_magnets_and_acestreams_from_row(row):
    """Extrae los enlaces Magnet y Acestream de una fila dada."""
    magnets = []
    acestreams = []
    links = row.find_all('a', href=True)

    for link in links:
        href = link.get('href', '')
        if 'magnet:' in href:
            magnet_hash = re.search(r'btih:[a-fA-F0-9]{40}', href)
            if magnet_hash:
                magnets.append(f"magnet:?xt=urn:{magnet_hash.group()}")
        elif 'acestream://' in href:
            acestreams.append(href)

    # Verificar hashes de Acestream directamente
    cols = row.find_all('td')
    if not links and len(cols) >= 2:
        raw_hash = cols[-1].text.strip()
        if len(raw_hash) == 40:  # Verificar si es un hash SHA-1
            acestreams.append(f"acestream://{raw_hash}")

    return magnets, acestreams


def extract_m3u_links(html_content):
    """Extrae enlaces de tipo m3u del contenido HTML."""
    streams = []
    lines = html_content.splitlines()

    current_stream = {}
    for line in lines:
        if line.startswith("#EXTINF:"):
            # Extraer metadatos de la línea #EXTINF
            match = re.search(r'tvg-logo="([^"]*)",(.+)', line)
            if match:
                logo_url, title = match.groups()
                current_stream = {
                    "title": title.strip(),
                    "logo": logo_url.strip(),
                    "links": []
                }
        elif line.startswith("acestream://"):
            # Si es un link acestream, lo añadimos al stream actual
            if current_stream:
                current_stream["links"].append(line.strip())
                streams.append(current_stream)
                current_stream = {}  # Limpiar para el siguiente stream

    return streams


def extract_stream_info(url):
    """Extrae la información de streams (Magnet y Acestream) de una página dada."""
    html_content = fetch_html_content(url)
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, 'html.parser')
    streams = []

    # Buscar todas las tablas
    tables = soup.find_all('table')

    if tables:
        # Recorrer todas las tablas para encontrar enlaces
        for streams_table in tables:
            rows = streams_table.find_all('tr')[1:]  # Ignorar la cabecera
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 2:  # Asegurarse de que haya suficientes columnas
                    stream_info = " - ".join([col.text.strip() for col in cols[:-1]])
                    magnets, acestreams = extract_magnets_and_acestreams_from_row(row)

                    if magnets or acestreams:
                        streams.append((stream_info, magnets + acestreams))

    # Buscar enlaces magnet fuera de las tablas (en listas no ordenadas)
    unordered_lists = soup.find_all('ul')
    for unordered_list in unordered_lists:
        list_items = unordered_list.find_all('li')
        for item in list_items:
            magnets = item.find_all('a', href=True)
            for magnet in magnets:
                href = magnet['href']
                if 'magnet:' in href:
                    magnet_hash = re.search(r'btih:[a-fA-F0-9]{40}', href)
                    if magnet_hash:
                        magnet_clean = f"magnet:?xt=urn:{magnet_hash.group()}"
                        title = item.get_text(strip=True).split('(torrent file)')[0].strip()
                        streams.append((title, [magnet_clean]))

    # Procesar enlaces tipo m3u si existen
    m3u_streams = extract_m3u_links(html_content)
    if m3u_streams:
        for stream in m3u_streams:
            streams.append((stream["title"], stream["links"]))

    return streams


def build_url(query):
    """Construye una URL con los parámetros proporcionados."""
    return f'{BASE_URL}?{urlencode(query)}'


def prompt_for_url():
    """Muestra un cuadro de diálogo para solicitar una nueva URL y la guarda en los ajustes."""
    current_url = ADDON.getSetting('scraper_url')
    dialog = xbmcgui.Dialog()
    
    warning_message = (
        "ADVERTENCIA: Asegúrese de que la URL proporcionada cumple con las leyes de su país. "
        "No apoyamos ni promovemos el acceso a contenido ilegal."
    )
    dialog.ok("Advertencia Legal", warning_message)
    
    new_url = dialog.input("Introduce la nueva URL a escanear", defaultt=current_url, type=xbmcgui.INPUT_ALPHANUM)

    # Si no se introduce una nueva URL, usar la anterior
    if not new_url:
        new_url = current_url

    if is_valid_url(new_url):
        # Guardar la nueva URL en los ajustes
        ADDON.setSetting('scraper_url', new_url)
        xbmcgui.Dialog().notification("URL actualizada", f"Se ha cambiado a: {new_url}", xbmcgui.NOTIFICATION_INFO, 3000)
        
        # Forzar la actualización del directorio actual
        xbmc.executebuiltin('Container.Refresh')
    else:
        xbmcgui.Dialog().notification("Error", "La URL proporcionada no es válida.", xbmcgui.NOTIFICATION_ERROR, 3000)


def list_streams():
    """Lista los streams en la interfaz de Kodi."""
    if not is_valid_url(SCRAPER_URL):
        xbmcgui.Dialog().ok("Error", "La URL proporcionada no es válida.")
        return

    streams = extract_stream_info(SCRAPER_URL)

    for stream_info, links in streams:
        for link in links:
            list_item = xbmcgui.ListItem(label=stream_info)
            list_item.setInfo("video", {"title": stream_info})

            if link.startswith("#"):
                # Esto es un comentario (e.g., fecha), no es un enlace reproducible
                xbmcplugin.addDirectoryItem(
                    handle=ADDON_HANDLE, url=link, listitem=list_item, isFolder=False
                )
            else:
                # Aquí verificamos si el enlace es un magnet o acestream
                if link.startswith("magnet:"):
                    # Extraemos el infohash del magnet
                    magnet_hash = re.search(r'btih:([a-fA-F0-9]{40})', link)
                    if magnet_hash:
                        infohash = magnet_hash.group(1)  # Obtener el hash
                        new_link = f"plugin://script.module.horus?action=play&infohash={infohash}"
                    else:
                        new_link = link  # Mantener el enlace original si no se puede extraer el hash
                    list_item.setArt({'icon': 'special://home/addons/plugin.video.extractor/resources/media/Magnet.png'})  # Establece el icono para magnet
                elif link.startswith("acestream://"):
                    # Extraemos el ID de Acestream
                    acestream_id = link.split("://")[1]  # Obtener solo la parte después de 'acestream://'
                    new_link = f"plugin://script.module.horus?action=play&id={acestream_id}"
                    list_item.setArt({'icon': 'special://home/addons/plugin.video.extractor/resources/media/Acestream.png'})  # Establece el icono para acestream
                else:
                    new_link = link  # Mantener el enlace original si no es ni acestream ni magnet
                    list_item.setArt({'icon': 'DefaultVideo.png'})  # Icono por defecto para otros enlaces

                list_item.setProperty("IsPlayable", "true")  # Indica que este ítem es reproducible
                xbmcplugin.addDirectoryItem(
                    handle=ADDON_HANDLE, url=new_link, listitem=list_item, isFolder=False
                )

    # Añadir opción para cambiar la URL sin mostrar la URL actual
    list_item_url = xbmcgui.ListItem(label="Cambiar o actualizar URL de origen")
    list_item_url.setArt({'icon': 'DefaultAddonsUpdates.png'})  # Establecer un ícono para cambiar URL
    xbmcplugin.addDirectoryItem(
        handle=ADDON_HANDLE, url=build_url({'action': 'change_url'}), listitem=list_item_url, isFolder=False
    )

    xbmcplugin.endOfDirectory(ADDON_HANDLE)


def show_links(title, links):
    """Muestra las opciones de enlaces para un stream en particular."""
    dialog = xbmcgui.Dialog()
    option_labels = [f"Opción {i + 1}" for i in range(len(links))]
    selected = dialog.select(f"Enlaces para {title}", option_labels)

    if selected != -1:
        xbmc.log(f"Seleccionado: {links[selected]}", xbmc.LOGINFO)
        xbmc.Player().play(links[selected])


def router(paramstring):
    """Lógica del enrutador basada en parámetros de la URL."""
    params = dict(parse_qsl(paramstring))
    action = params.get('action')

    if action == 'show_links':
        title = params.get('title')
        links = eval(params.get('links'))  # Convertir a lista de cadenas
        show_links(title, links)
    elif action == 'change_url':
        prompt_for_url()  # Llama a la función para cambiar la URL
    else:
        list_streams()


if __name__ == '__main__':
    if len(sys.argv) > 2:
        router(sys.argv[2][1:])
    else:
        router('')
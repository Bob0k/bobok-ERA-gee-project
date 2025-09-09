import os
import sqlite3

from datetime import date


def create_database_files(foldername: str, search_database: str, tiles_database: str, ee_database: str, servers):
    search_database = os.path.join(foldername, search_database + ".db")
    tiles_database = os.path.join(foldername, tiles_database + ".db")
    ee_database = os.path.join(foldername, ee_database + ".db")

    if not os.path.exists(foldername):
        os.mkdir(foldername)
        print("dbs folder created")

    if not os.path.exists(search_database):
        print("Can't connect to ", search_database)
        connection = sqlite3.connect(search_database)
        cursor = connection.cursor()
        for command in [
            """CREATE TABLE "locations" ( 
            "i" INTEGER NOT NULL UNIQUE, 
            "address" TEXT NOT NULL UNIQUE, 
            "south" REAL, 
            "west" REAL, 
            "east" REAL, 
            "north" REAL, 
            "lat" REAL NOT NULL, 
            "lng" REAL NOT NULL, 
            PRIMARY KEY("i" AUTOINCREMENT) );""",

            """CREATE TABLE "requests" ( 
            "request" TEXT NOT NULL UNIQUE, 
            "link" INTEGER NOT NULL, 
            FOREIGN KEY("link") REFERENCES "locations"("i") );"""
        ]:
            cursor.execute(command)

        connection.commit()
        connection.close()
        print("Created", search_database)

    else:
        print("Connected to", search_database)

    if not os.path.exists(tiles_database):
        print("Can't connect to ", tiles_database)
        connection = sqlite3.connect(tiles_database)
        cursor = connection.cursor()
        for command in (
                [
                    """CREATE TABLE server (
                        url VARCHAR(300) PRIMARY KEY NOT NULL,
                        max_zoom INTEGER NOT NULL);"""
                ] + [
                    f"""INSERT INTO server (url, max_zoom) 
                    VALUES ("{server[1]}", {server[2]}); """ for server in servers
                ] + [
                    """CREATE TABLE tiles ( 
                        zoom INTEGER NOT NULL, 
                        x INTEGER NOT NULL, 
                        y INTEGER NOT NULL, 
                        server VARCHAR(300) NOT NULL, 
                        tile_image BLOB NOT NULL, 
                        CONSTRAINT fk_server FOREIGN KEY (server) REFERENCES server (url), 
                        CONSTRAINT pk_tiles PRIMARY KEY (zoom, x, y, server));"""
                ]):
            cursor.execute(command)

        connection.commit()
        connection.close()
        print("Created", tiles_database)

    else:
        print("Connected to", tiles_database)
        connection = sqlite3.connect(tiles_database)
        cursor = connection.cursor()
        for name, url, zoom in servers:
            cursor.execute("""SELECT url FROM server WHERE url=?;""", (url,))
            res = cursor.fetchone()
            if res is None:
                cursor.execute("""INSERT INTO server (url, max_zoom) VALUES (?, ?);""", (url, zoom))

        connection.commit()
        connection.close()

    if not os.path.exists(ee_database):
        print("Can't connect to", ee_database)
        connection = sqlite3.connect(ee_database)
        cursor = connection.cursor()
        command = """CREATE TABLE "images" (
                        "id"	INTEGER NOT NULL UNIQUE,
                        "tlxd"	REAL NOT NULL,
                        "tlyd"	REAL NOT NULL,
                        "brxd"	REAL NOT NULL,
                        "bryd"	REAL NOT NULL,
                        "fdate"	TEXT NOT NULL,
                        "ldate"	TEXT NOT NULL,
                        "cloudiness"	TEXT NOT NULL,
                        "image" BLOB NOT NULL,
                        PRIMARY KEY("id" AUTOINCREMENT)
                );"""
        cursor.execute(command)
        connection.commit()
        connection.close()
        print("Created", ee_database)

    else:
        print("Connected to", ee_database)

    return search_database, tiles_database, ee_database


def before_start():
    return
    print("Connection to databases")
    os.system("taskkill /IM RimWorldWin64.exe")
    print("Connected to databases")


# Collections
collections = (
    ("COPERNICUS", "COPERNICUS/S2_SR_HARMONIZED"),
               )

# Server name, server url, max zoom
servers = (
    ("OpenStreetMap", "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png", 18),
    ("Google карты", "https://mt0.google.com/vt/lyrs=m&hl=en&x={x}&y={y}&z={z}&s=Ga", 22),
    ("Google спутник", "https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}&s=Ga", 22),
    ("Humanitarian", "https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png", 18),
    ("CyclOSM", "https://a.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png", 18),
    ("OpenTopoMap", "https://a.tile.opentopomap.org/{z}/{x}/{y}.png", 18),
    ("OSM France", "https://a.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png", 18),

)

HIDE_PROXY = False

DATA_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), "data")  # Includes absolute path to the main.py
SEARCH_DATABASE_PATH, DATABASE_PATH, EE_DATABASE_PATH = create_database_files(
    DATA_FOLDER, "keyed_search_database", "offline_map_tiles6", "ee_tiles",
    servers
)
LOGO_FILENAME = "logo_light.png"
THEME_FILENAME = "theme.json"
ICON_FILENAME = "icon.ico"
CORNER_FILENAME = "top_left_corner.png"
BR_CORNER_FILENAME = "bottom_right_corner.png"
LAST_PROXY_FILENAME = "last_proxy.txt"
VIEW_ICON_FILENAME = "opened_eye.png"
HIDE_ICON_FILENAME = "hidden_eye.png"
FIND_ICON_FILENAME = "find.png"
DELETE_ICON_FILENAME = "trash.png"

DEFAULT_DATE_UNTIL = date.today()
if DEFAULT_DATE_UNTIL.month == 1:
    DEFAULT_DATE_FROM = DEFAULT_DATE_UNTIL.replace(month=12, year=DEFAULT_DATE_UNTIL.year - 1)
else:
    DEFAULT_DATE_FROM = DEFAULT_DATE_UNTIL.replace(month=DEFAULT_DATE_UNTIL.month - 1)

# == Colors ==
# Connection
UNKNOWN_COLOR = "#999999"
DISCONNECTED_COLOR = "#FF0000"
CONNECTED_COLOR = "#00FF00"
# Buttons fg_color=("#CCCCCC", "#222222")
CHOSEN_FOLDER = "#CCCCCC"
UNCHOSEN_FOLDER = "#c33939"

try:
    with open(os.path.join(DATA_FOLDER, LAST_PROXY_FILENAME)) as f:
        DEFAULT_PROXY = f.read()

except Exception as e:
    print("Failed proxy import because of ", e)
    DEFAULT_PROXY = ""

# Translator
RU_KEYS = "йцукенгшщзхъфывапролджэячсмитьбюЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ"
EN_KEYS = "qwertyuiop[]asdfghjkl;'zxcvbnm,.QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>"
def translate(entry):
    is_rus = entry[0] in RU_KEYS
    from_chars = RU_KEYS if is_rus else EN_KEYS
    to_chars = EN_KEYS if is_rus else RU_KEYS
    result = ""
    for character in entry:
        result += to_chars[from_chars.find(character)]
    return result

# Theme names
LIGHT_MODE_NAME = "Светлая"
DARK_MODE_NAME = "Темная"

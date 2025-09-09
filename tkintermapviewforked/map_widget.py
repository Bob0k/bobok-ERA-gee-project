import requests
import math
import threading
import tkinter
import tkinter.ttk as ttk
import tkinter.messagebox
import time
import PIL
import sys
import io
import sqlite3
import pyperclip
import geocoder
from datetime import datetime
from PIL import Image, ImageTk
from typing import Callable, List, Dict, Union, Tuple
from functools import partial

import numpy

from .canvas_position_marker import CanvasPositionMarker
from .canvas_tile import CanvasTile
from .utility_functions import decimal_to_osm, osm_to_decimal
from .canvas_button import CanvasButton
from .canvas_path import CanvasPath
from .canvas_polygon import CanvasPolygon
from .canvas_ee_image import CanvasEEImage

import ee
import geemap

EE_IMAGE_DARKNESS = 10
EE_IMAGE_SHOW_DISTANCE = 0.1

class TkinterMapView(tkinter.Frame):
    def __init__(self, *args,
                 width: int = 300,
                 height: int = 200,
                 corner_radius: int = 0,
                 bg_color: str = None,
                 database_path: str = None,
                 ee_database_path: str = None,
                 use_database_only: bool = False,
                 search_database_path: str = None,
                 autosave: bool = False,
                 max_zoom: int = 19,
                 set_connection_status=None,
                 get_connection_status=None,
                 eeid: list[int]=None,
                 **kwargs):
        super().__init__(*args, **kwargs)

        self.running = True
        self.eeid = eeid

        self.width = width
        self.height = height
        self.corner_radius = corner_radius if corner_radius <= 30 else 30  # corner_radius can't be greater than 30
        self.configure(width=self.width, height=self.height)
        # detect color of master widget for rounded corners
        if bg_color is None:
            # map widget is placed in a CTkFrame from customtkinter library
            if ((hasattr(self.master, "canvas")
                and hasattr(self.master, "fg_color"))
                    or (hasattr(self.master, "_canvas")
                        and hasattr(self.master, "_fg_color"))):
                # customtkinter version >=5.0.0
                if hasattr(self.master, "_apply_appearance_mode"):
                    self.bg_color: str = self.master._apply_appearance_mode(self.master.cget("fg_color"))
                # customtkinter version <=4.6.3
                elif hasattr(self.master, "fg_color"):
                    if type(self.master.fg_color) is tuple or type(self.master.fg_color) is list:
                        self.bg_color: str = self.master.fg_color[self.master._appearance_mode]
                    else:
                        self.bg_color: str = self.master.fg_color

            # map widget is placed on a tkinter.Frame or tkinter.Tk
            elif isinstance(self.master, (tkinter.Frame, tkinter.Tk, tkinter.Toplevel, tkinter.LabelFrame)):
                self.bg_color: str = self.master.cget("bg")

            # map widget is placed in a ttk widget
            elif isinstance(self.master, (ttk.Frame, ttk.LabelFrame, ttk.Notebook)):
                try:
                    ttk_style = ttk.Style()
                    self.bg_color = ttk_style.lookup(self.master.winfo_class(), 'background')
                except Exception:
                    self.bg_color: str = "#000000"

            # map widget is placed on an unknown widget
            else:
                self.bg_color: str = "#000000"
        else:
            self.bg_color = bg_color

        self.grid_rowconfigure(0, weight=1)  # configure 1x1 grid system
        self.grid_columnconfigure(0, weight=1)

        self.canvas = tkinter.Canvas(master=self,
                                     highlightthickness=0,
                                     bg="#F1EFEA",
                                     width=self.width,
                                     height=self.height)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # zoom buttons
        self.button_zoom_in = CanvasButton(self, (20, 20), text="+", command=self.button_zoom_in)
        self.button_zoom_out = CanvasButton(self, (20, 60), text="-", command=self.button_zoom_out)

        button_polygon_position = 100
        # Connection status
        self.set_connection_status = set_connection_status
        if self.set_connection_status is None:
            self.set_connection_status = self.default_set_connection_status
            self.button_connection = CanvasButton(self, (20, 100), text="?", command=self.button_connection)
            button_polygon_position += 40
        self.get_connection_status = get_connection_status
        if self.get_connection_status is None:
            self.get_connection_status = self.default_get_connection_status

        # ■■□□
        self.button_polygon = CanvasButton(self, (20, button_polygon_position),
                                           text="□", command=self.switch_polygon_draw)


        # bind events for mouse button pressed, mouse movement, and scrolling
        self.canvas.bind("<B1-Motion>", self.mouse_move)
        self.canvas.bind("<Button-1>", self.mouse_click)
        self.canvas.bind("<ButtonRelease-1>", self.mouse_release)
        self.canvas.bind("<MouseWheel>", self.mouse_zoom)
        self.canvas.bind("<Button-4>", self.mouse_zoom)
        self.canvas.bind("<Button-5>", self.mouse_zoom)
        self.bind('<Configure>', self.update_dimensions)
        self.last_mouse_down_position: Union[tuple, None] = None
        self.last_mouse_down_time: Union[float, None] = None
        self.mouse_click_position: Union[tuple, None] = None
        self.map_click_callback: Union[Callable, None] = None  # callback function for left click on map

        # movement fading
        self.fading_possible: bool = True
        self.move_velocity: Tuple[float, float] = (0, 0)
        self.last_move_time: Union[float, None] = None

        # describes the tile layout
        self.zoom: float = 0
        self.upper_left_tile_pos: Tuple[float, float] = (0, 0)  # in OSM coords
        self.lower_right_tile_pos: Tuple[float, float] = (0, 0)
        self.tile_size: int = 256  # in pixel
        self.last_zoom: float = self.zoom

        # canvas objects, image cache and standard empty images
        self.canvas_tile_array: List[List[CanvasTile]] = []
        self.canvas_marker_list: List[CanvasPositionMarker] = []
        self.canvas_path_list: List[CanvasPath] = []
        self.canvas_polygon_list: List[CanvasPolygon] = []

        self.tile_image_cache: Dict[str, PIL.ImageTk.PhotoImage] = {}
        self.empty_tile_image = ImageTk.PhotoImage(Image.new("RGB", (self.tile_size, self.tile_size), (190, 190, 190)))  # used for zooming and moving
        self.not_loaded_tile_image = ImageTk.PhotoImage(Image.new("RGB", (self.tile_size, self.tile_size), (250, 250, 250)))  # only used when image not found on tile server

        # tile server and database
        self.tile_server = "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"
        self.database_path = database_path
        self.use_database_only = use_database_only
        self.autosave = autosave
        self.overlay_tile_server: Union[str, None] = None
        self.max_zoom = max_zoom  # should be set according to tile server max zoom
        self.min_zoom: int = math.ceil(math.log2(math.ceil(self.width / self.tile_size)))  # min zoom at which map completely fills widget
        # create tables if there is none
        if self.database_path is not None:
            db_connection = sqlite3.connect(self.database_path)
            db_cursor = db_connection.cursor()
            # create tables if it not exists
            # create_server_table = """CREATE TABLE IF NOT EXISTS server (
            #                                         url VARCHAR(300) PRIMARY KEY NOT NULL,
            #                                         max_zoom INTEGER NOT NULL);"""

            create_tiles_table = """CREATE TABLE IF NOT EXISTS tiles (
                                                    zoom INTEGER NOT NULL,
                                                    x INTEGER NOT NULL,
                                                    y INTEGER NOT NULL,
                                                    server VARCHAR(300) NOT NULL,
                                                    tile_image BLOB NOT NULL,
                                                    CONSTRAINT fk_server FOREIGN KEY (server) REFERENCES server (url),
                                                    CONSTRAINT pk_tiles PRIMARY KEY (zoom, x, y, server));"""

            # create_sections_table = """CREATE TABLE IF NOT EXISTS sections (
            #                                             position_a VARCHAR(100) NOT NULL,
            #                                             position_b VARCHAR(100) NOT NULL,
            #                                             zoom_a INTEGER NOT NULL,
            #                                             zoom_b INTEGER NOT NULL,
            #                                             server VARCHAR(300) NOT NULL,
            #                                             CONSTRAINT fk_server FOREIGN KEY (server) REFERENCES server (url),
            #                                             CONSTRAINT pk_tiles PRIMARY KEY (position_a, position_b, zoom_a, zoom_b, server));"""

            # db_cursor.execute(create_server_table)
            db_cursor.execute(create_tiles_table)
            # db_cursor.execute(create_sections_table)
            db_connection.commit()
            db_connection.close()

        # search storage
        self.search_database_path = search_database_path

        # ee compatibility
        self.is_ee_authenticated = False
        self.ee_database_path = ee_database_path
        self.use_ee_database = True
        self.canvas_ee_image_list: List[CanvasEEImage] = []
        self.ee_collection = None
        # ee settings
        self.date_from = None
        self.date_until = None
        self.cloudiness = None

        # polygon settings
        self.is_regime_polygon = False
        self.is_drawing_polygon = False
        self.region_polygon = None

        # pre caching for smoother movements (load tile images into cache at a certain radius around the pre_cache_position)
        self.pre_cache_position: Union[Tuple[float, float], None] = None
        self.pre_cache_thread = threading.Thread(daemon=True, target=self.pre_cache)
        self.pre_cache_thread.start()

        # image loading in background threads
        self.image_load_queue_tasks: List[tuple] = []  # task: ((zoom, x, y), canvas_tile_object)
        self.image_load_queue_results: List[tuple] = []  # result: ((zoom, x, y), canvas_tile_object, photo_image)
        self.after(10, self.update_canvas_tile_images)
        self.image_load_thread_pool: List[threading.Thread] = []

        # add background threads which load tile images from self.image_load_queue_tasks
        for i in range(25):
            image_load_thread = threading.Thread(daemon=True, target=self.load_images_background)
            image_load_thread.start()
            self.image_load_thread_pool.append(image_load_thread)

        # set initial position
        self.set_zoom(17)
        self.set_position(52.516268, 13.377695)  # Brandenburger Tor, Berlin

        # right click menu
        self.right_click_menu_commands: List[dict] = []  # list of dictionaries with "label": str, "command": Callable, "pass_coords": bool
        if sys.platform == "darwin":
            self.canvas.bind("<Button-2>", self.mouse_right_click)
        else:
            self.canvas.bind("<Button-3>", self.mouse_right_click)

        self.draw_rounded_corners()

        self.last_filter_position = [1000, 1000]
        self.initiate_filtering()

        self.to_crop_queue = []
        self.crop_thread = threading.Thread(daemon=True, target=self.crop_and_add_image_thread)

    def default_get_connection_status(self):
        return self.button_connection.text

    def default_set_connection_status(self, status: bool):
        if self.use_database_only:
            self.button_connection.text = "x"
            self.button_connection.draw()
            return

        if status:
            self.button_connection.text = "1"
            self.set_tile_server(self.tile_server)

        else:
            self.button_connection.text = "0"

        self.button_connection.draw()

    def destroy(self):
        self.running = False
        super().destroy()

    def draw_rounded_corners(self):
        self.canvas.delete("corner")

        if sys.platform.startswith("win"):
            pos_corr = -1
        else:
            pos_corr = 0

        if self.corner_radius > 0:
            radius = self.corner_radius
            self.canvas.create_arc(self.width - 2 * radius + 5 + pos_corr, self.height - 2 * radius + 5 + pos_corr,
                                   self.width + 5 + pos_corr, self.height + 5 + pos_corr,
                                   style=tkinter.ARC, tag="corner", width=10, outline=self.bg_color, start=-90)
            self.canvas.create_arc(2 * radius - 5, self.height - 2 * radius + 5 + pos_corr, -5, self.height + 5 + pos_corr,
                                   style=tkinter.ARC, tag="corner", width=10, outline=self.bg_color, start=180)
            self.canvas.create_arc(-5, -5, 2 * radius - 5, 2 * radius - 5,
                                   style=tkinter.ARC, tag="corner", width=10, outline=self.bg_color, start=-270)
            self.canvas.create_arc(self.width - 2 * radius + 5 + pos_corr, -5, self.width + 5 + pos_corr, 2 * radius - 5,
                                   style=tkinter.ARC, tag="corner", width=10, outline=self.bg_color, start=0)

    def update_dimensions(self, event):
        # only redraw if dimensions changed (for performance)
        if self.width != event.width or self.height != event.height:
            self.width = event.width
            self.height = event.height
            self.min_zoom = math.ceil(math.log2(math.ceil(self.width / self.tile_size)))

            self.set_zoom(self.zoom)  # call zoom to set the position vertices right
            self.draw_move()  # call move to draw new tiles or delete tiles
            self.draw_rounded_corners()

    def add_right_click_menu_command(self, label: str, command: Callable, pass_coords: bool = False) -> None:
        self.right_click_menu_commands.append({"label": label, "command": command, "pass_coords": pass_coords})

    def add_left_click_map_command(self, callback_function):
        self.map_click_callback = callback_function

    def convert_canvas_coords_to_decimal_coords(self, canvas_x: int, canvas_y: int) -> tuple:
        relative_mouse_x = canvas_x / self.canvas.winfo_width()
        relative_mouse_y = canvas_y / self.canvas.winfo_height()

        tile_mouse_x = self.upper_left_tile_pos[0] + (self.lower_right_tile_pos[0] - self.upper_left_tile_pos[0]) * relative_mouse_x
        tile_mouse_y = self.upper_left_tile_pos[1] + (self.lower_right_tile_pos[1] - self.upper_left_tile_pos[1]) * relative_mouse_y

        coordinate_mouse_pos = osm_to_decimal(tile_mouse_x, tile_mouse_y, round(self.zoom))
        return coordinate_mouse_pos

    def toggle_autosave(self):
        self.autosave = not self.autosave

    def mouse_right_click(self, event):
        coordinate_mouse_pos = self.convert_canvas_coords_to_decimal_coords(event.x, event.y)

        def click_coordinates_event():
            try:
                pyperclip.copy(f"{coordinate_mouse_pos[0]:.7f}, {coordinate_mouse_pos[1]:.7f}")
                tkinter.messagebox.showinfo(title="", message="Coordinates copied to clipboard!")

            except Exception as err:
                if sys.platform.startswith("linux"):
                    tkinter.messagebox.showinfo(title="", message="Error copying to clipboard.\n" + str(err) + "\n\nTry to install xclip:\n'sudo apt-get install xclip'")

                else:
                    tkinter.messagebox.showinfo(title="", message="Error copying to clipboard.\n" + str(err))

        m = tkinter.Menu(self, tearoff=0)
        m.add_command(label=f"{coordinate_mouse_pos[0]:.7f} {coordinate_mouse_pos[1]:.7f}",
                      command=click_coordinates_event)

        m.add_command(label=f"{'Выключить автосохранение' if self.autosave else 'Включить автосохранение'}",
                      command=self.toggle_autosave)

        if len(self.right_click_menu_commands) > 0:
            m.add_separator()

        for command in self.right_click_menu_commands:
            if command["pass_coords"]:
                m.add_command(label=command["label"], command=partial(command["command"], coordinate_mouse_pos))

            else:
                m.add_command(label=command["label"], command=command["command"])

        m.tk_popup(event.x_root, event.y_root)  # display menu

    def set_overlay_tile_server(self, overlay_server: str):
        self.overlay_tile_server = overlay_server

    def set_tile_server(self, tile_server: str, tile_size: int = 256, max_zoom: int = 19):
        self.image_load_queue_tasks = []
        self.max_zoom = max_zoom
        self.tile_size = tile_size
        self.min_zoom = math.ceil(math.log2(math.ceil(self.width / self.tile_size)))
        self.tile_server = tile_server
        self.tile_image_cache: Dict[str, PIL.ImageTk.PhotoImage] = {}
        self.canvas.delete("tile")
        self.image_load_queue_results = []
        self.draw_initial_array()

    def get_position(self) -> tuple:
        """ returns current middle position of map widget in decimal coordinates """

        return osm_to_decimal((self.lower_right_tile_pos[0] + self.upper_left_tile_pos[0]) / 2,
                              (self.lower_right_tile_pos[1] + self.upper_left_tile_pos[1]) / 2,
                              round(self.zoom))

    def fit_bounding_box(self, position_top_left: Tuple[float, float], position_bottom_right: Tuple[float, float]):
        # wait 200ms till method is called, because dimensions have to update first
        self.after(100, self._fit_bounding_box, position_top_left, position_bottom_right)

    def _fit_bounding_box(self, position_top_left: Tuple[float, float], position_bottom_right: Tuple[float, float]):
        """ Fit the map to contain a bounding box with the maximum zoom level possible. """

        # check positions
        if not (position_top_left[0] > position_bottom_right[0] and position_top_left[1] < position_bottom_right[1]):
            raise ValueError("incorrect bounding box positions, <must be top_left_position> <bottom_right_position>")

        # update idle-tasks to make sure current dimensions are correct
        self.update_idletasks()

        last_fitting_zoom_level = self.min_zoom
        middle_position_lat, middle_position_long = (position_bottom_right[0] + position_top_left[0]) / 2, (position_bottom_right[1] + position_top_left[1]) / 2

        # loop through zoom levels beginning at minimum zoom
        for zoom in range(self.min_zoom, self.max_zoom + 1):
            # calculate tile positions for bounding box
            middle_tile_position = decimal_to_osm(middle_position_lat, middle_position_long, zoom)
            top_left_tile_position = decimal_to_osm(*position_top_left, zoom)
            bottom_right_tile_position = decimal_to_osm(*position_bottom_right, zoom)

            # calculate tile positions for map corners
            calc_top_left_tile_position = (middle_tile_position[0] - ((self.width / 2) / self.tile_size),
                                           middle_tile_position[1] - ((self.height / 2) / self.tile_size))
            calc_bottom_right_tile_position = (middle_tile_position[0] + ((self.width / 2) / self.tile_size),
                                               middle_tile_position[1] + ((self.height / 2) / self.tile_size))

            # check if bounding box fits in map
            if calc_top_left_tile_position[0] < top_left_tile_position[0] and calc_top_left_tile_position[1] < top_left_tile_position[1] \
                    and calc_bottom_right_tile_position[0] > bottom_right_tile_position[0] and calc_bottom_right_tile_position[1] > bottom_right_tile_position[1]:
                # set last_fitting_zoom_level to current zoom becuase bounding box fits in map
                last_fitting_zoom_level = zoom

            else:
                # break because bounding box does not fit in map
                break

        # set zoom to last fitting zoom and position to middle position of bounding box
        self.set_zoom(last_fitting_zoom_level)
        self.set_position(middle_position_lat, middle_position_long)

    def set_position(self, deg_x, deg_y, text=None, marker=False, **kwargs) -> CanvasPositionMarker:
        """ set new middle position of map in decimal coordinates """

        # convert given decimal coordinates to OSM coordinates and set corner positions accordingly
        current_tile_position = decimal_to_osm(deg_x, deg_y, round(self.zoom))
        self.upper_left_tile_pos = (current_tile_position[0] - ((self.width / 2) / self.tile_size),
                                    current_tile_position[1] - ((self.height / 2) / self.tile_size))

        self.lower_right_tile_pos = (current_tile_position[0] + ((self.width / 2) / self.tile_size),
                                     current_tile_position[1] + ((self.height / 2) / self.tile_size))

        if marker is True:
            marker_object = self.set_marker(deg_x, deg_y, text, **kwargs)

        else:
            marker_object = None

        self.check_map_border_crossing()
        self.draw_initial_array()
        # self.draw_move() ausreichend?

        return marker_object

    def set_address(self, address_string: str | int, marker: bool = False, text: str = None, **kwargs) -> Tuple[int, str]:
        """ Function uses geocode service of OpenStreetMap (Nominatim).
            https://geocoder.readthedocs.io/providers/OpenStreetMap.html """

        location = None

        # try to select location in database
        if self.search_database_path is not None:
            db_connection = sqlite3.connect(self.search_database_path)
            db_cursor = db_connection.cursor()

            command = """SELECT l.i, l.address, l.lat, l.lng, l.south, l.west, l.east, l.north
                           FROM requests r, locations l 
                          WHERE r.request=? AND r.link=l.i;"""
            if type(address_string) is int:
                command = """SELECT l.i, l.address, l.lat, l.lng, l.south, l.west, l.east, l.north
                               FROM locations l
                              WHERE l.i=?"""

            db_cursor.execute(command, (address_string,))
            location = db_cursor.fetchone()

        if location is None:
            location = geocoder.osm(address_string)

            # there is no such location
            if not location.ok:
                return None, None

            # print("From OSM")
            address, lat, lng = location.address, location.lat, location.lng
            south, west, east, north = location.south, location.west, location.east, location.north

            # save result
            if self.search_database_path is not None:
                # try to select address which we got
                select_command = "SELECT i FROM locations WHERE address=?;"
                db_cursor.execute(select_command, (address,))
                i = db_cursor.fetchone()

                # insert location if there is no yet
                if i is None:
                    command = "INSERT INTO locations (address, lat, lng, north, east, south, west) VALUES (?, ?, ?, ?, ?, ?, ?);"
                    db_cursor.execute(command, (address, lat, lng, north, east, south, west))

                db_cursor.execute(select_command, (address,))
                i = db_cursor.fetchone()[0]

                command = "INSERT INTO requests (request, link) VALUES (?, ?);"
                db_cursor.execute(command, (address_string, i))
                db_connection.commit()

        else:
            # print("From database")
            i, address, lat, lng, south, west, east, north = location

        # determine zoom level for result by bounding box
        zoom_not_possible = True
        for zoom in range(self.min_zoom, self.max_zoom + 1):
            lower_left_corner = decimal_to_osm(south, west, zoom)
            upper_right_corner = decimal_to_osm(north, east, zoom)
            tile_width = upper_right_corner[0] - lower_left_corner[0]

            if tile_width > math.floor(self.width / self.tile_size):
                zoom_not_possible = False
                self.set_zoom(zoom)
                break

        if zoom_not_possible:
            self.set_zoom(self.max_zoom)

        self.set_position(lat, lng)
        return i, address

    def set_marker(self, deg_x: float, deg_y: float, text: str = None, **kwargs) -> CanvasPositionMarker:
        marker = CanvasPositionMarker(self, (deg_x, deg_y), text=text, **kwargs)
        marker.draw()
        self.canvas_marker_list.append(marker)
        return marker


    # === Earth Engine ===

    def set_ee_settings_vars(self,
                             date_from: str = None,
                             date_until: str = None,
                             cloudiness: int = None):

        date_from = datetime(*tuple(int(d) for d in date_from.split("-")))
        date_until = datetime(*tuple(int(d) for d in date_until.split("-")))

        if date_from is not None:
            self.date_from = date_from

        if date_until is not None:
            self.date_until = date_until

        if cloudiness is not None:
            self.cloudiness = cloudiness

        #print(f"self.cloudiness = {self.cloudiness}, cloudiness.get() = {cloudiness}")


    def ee_authenticate_thread(self, on_authentication, on_fail):
        try:
            print("Authenticating in Earth Engine")
            ee.Authenticate()
            ee.Initialize(project="ee-era")
            print("Earth Engine authenticated")
            self.is_ee_authenticated = True
            if on_authentication is not None:
                on_authentication()

        except Exception as e:
            print("Failed Earth Engine authentication:\n\t")
            print(e)

            if on_fail is not None:
                on_fail()

    def ee_authenticate(self, on_authentication=None, on_fail=None):
        if self.is_ee_authenticated:
            print("Earth Engine is already authenticated")
            return

        ee_thread = threading.Thread(daemon=True, target=self.ee_authenticate_thread, args=(on_authentication, on_fail))
        ee_thread.start()

    @staticmethod
    def numpy_to_image(npimage):
        # def color_function(cell):
        #     new_cell = []
        arr = numpy.array([[[min(255, color/EE_IMAGE_DARKNESS) for color in cell] for cell in row] for row in npimage])

        img = Image.fromarray((
                    arr
            ).astype("uint8"))

        # Find border to crop
        min_x = img.size[0]
        max_x = 0
        min_y = img.size[1]
        max_y = 0
        for x in range(img.size[0]):
            for y in range(img.size[1]):
                color = img.getpixel(xy=(x, y))
                if color != (0, 0, 0):
                    min_x = x if x < min_x else min_x
                    max_x = x if x > max_x else max_x
                    min_y = y if y < min_y else min_y
                    max_y = y if y > max_y else max_y
        max_x += 1
        max_y += 1

        # Get proportion of part to crop
        from_top = min_y / img.size[1]
        from_bottom = 1 - max_y / img.size[1]
        from_left = min_x / img.size[0]
        from_right = 1 - max_x / img.size[0]

        cimg = img.crop((min_x, min_y, max_x, max_y)).convert(mode="RGBA")

        # Convert remaining black pixels to transparent pixels
        for x in range(cimg.size[0]):
            for y in range(cimg.size[1]):
                if cimg.getpixel(xy=(x, y)) == (0, 0, 0, 255):
                    cimg.putpixel(xy=(x, y), value=(0, 0, 0, 0))

        return cimg, from_left, from_right, from_top, from_bottom, img

    def save_ee_image(self, pilimage, tlxd, tlyd, brxd, bryd, fdate, ldate, cloudiness):
        """Saves an EE image to the database"""
        db_connection = sqlite3.connect(self.ee_database_path)
        db_cursor = db_connection.cursor()
        buffer = io.BytesIO()
        pilimage.save(buffer, format="PNG")
        db_cursor.execute("""INSERT INTO images (tlxd, tlyd, brxd, bryd, fdate, ldate, cloudiness, image) VALUES (?, ?, ?, ?, ?, ?, ?, ?);""",
                          (tlxd, tlyd, brxd, bryd, fdate, ldate, cloudiness, buffer.getvalue()))
        db_connection.commit()
        db_connection.close()

    def crop_and_add_image_thread(self):
        """Crops images and adds them"""
        while self.to_crop_queue:

            tlxd, tlyd, brxd, bryd, fdate, ldate, cloud, rgb_img = self.to_crop_queue.pop()

            pilimage, from_left, from_right, from_top, from_bottom, defimage = self.numpy_to_image(rgb_img)
            print("Successfully cropped image")

            ntlxd, nbrxd, ntlyd, nbryd = (tlxd * (1 - from_top) + brxd * (from_top),
                                          tlxd * (from_bottom) + brxd * (1 - from_bottom),
                                          tlyd * (1 - from_left) + bryd * from_left,
                                          tlyd * from_right + bryd * (1 - from_right))

            total_eeid = self.eeid[0]
            self.eeid[0] += 1

            try:
                self.add_ee_image(eeid=total_eeid,
                                  position=(ntlxd, ntlyd),
                                  brposition=(nbrxd, nbryd),
                                  image=pilimage,
                                  fdate=fdate,
                                  ldate=ldate,
                                  cloudiness=cloud)

                # Save cropped image
                try:
                    self.save_ee_image(
                        pilimage=pilimage,
                        tlxd=ntlxd,
                        tlyd=ntlyd,
                        brxd=nbrxd,
                        bryd=nbryd,
                        fdate=fdate,
                        ldate=ldate,
                        cloudiness=cloud)

                except Exception as e:
                    print("Failed to save image ", e)

                self.master.master.render_image_frame(item=(total_eeid, ntlxd, ntlyd,
                                                            nbrxd, nbryd, fdate, ldate, cloud, pilimage), new=True)
                self.initiate_filtering(forced=True)

            except Exception as e:
                # Add uncropped and opaque image if any error occur
                print("Failed image adding because of:\n\t", end="")
                print(e, "\nAdded default image instead")
                self.add_ee_image(eeid=total_eeid,
                                  position=(tlxd, tlyd),
                                  brposition=(brxd, bryd),
                                  image=defimage,
                                  fdate=fdate,
                                  ldate=ldate,
                                  cloudiness=cloud)

            finally:
                self.master.master.number_of_images_downloading -= 1

                if self.master.master.number_of_images_downloading < 0:
                    print("Something went wrong")

                if self.master.master.number_of_images_downloading == 0:
                    self.master.master.reset_download_button()

    def get_ee_image_thread(self, tlxd, tlyd, brxd, bryd, fdate, ldate, cloud):
        """This function downloads an image in numpy array and appends it to the
           list of images to crop and add to the system"""
        self.master.master.number_of_images_downloading += 1
        bbox = ee.Geometry.BBox(tlyd, brxd, bryd, tlxd)

        if self.ee_collection is None:
            self.ee_collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')

        ee_image = (self.ee_collection
                    .filterBounds(bbox)  # Фильтруем по области
                    .filterDate(fdate, ldate)  # Укажите нужный диапазон дат example: '2023-09-30' YYYY-MM-DD
                    #.filter(ee.Filter.gt('CLOUDY_PIXEL_PERCENTAGE', max(0, cloud - 10)))
                    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', min(100, cloud + 10)))
                    #.sort('CLOUDY_PIXEL_PERCENTAGE')
                    .sort('system:time_start', False)  # Сортируем по времени (последние изображения первыми)
                    # .select(['B4', 'B3', 'B2'])
                    .first())  # Берем первое изображение

        print("Downloading image")

        try:
            rgb_img = geemap.ee_to_numpy(ee_image, bands=['B4', 'B3', 'B2'],
                                         region=bbox, scale=self.master.master.get_scale())
            print("Successfully downloaded image")

            self.to_crop_queue.append((tlxd, tlyd, brxd, bryd, fdate, ldate, cloud, rgb_img))

            if not self.crop_thread.is_alive():
                self.crop_thread.run()

        except Exception as e:

            if not str(e).startswith("Total"):
                # Generic exception handle
                raise Exception(e)

            # Too large image exception handle
            print("Split")
            center_x = (tlxd + brxd) / 2
            center_y = (tlyd + bryd) / 2

            corners = [(tlxd, tlyd, center_x, center_y),  # Top left
                       (tlxd, center_y, center_x, bryd),  # Top right
                       (center_x, tlyd, brxd, center_y),  # Bottom left
                       (center_x, center_y, brxd, bryd)]  # Bottom right
            for index, corner in enumerate(corners):
                ee_image_thread = threading.Thread(daemon=True,
                                                   target=self.get_ee_image_thread,
                                                   args=corner + (fdate, ldate, cloud)
                                                   )
                ee_image_thread.start()

    def get_ee_image_depr(self, top_left: Tuple[float, float], bottom_right: Tuple[float, float],
                          date_from: str, date_until: str, cloudiness: int, forced: bool = False):
        if not forced:
            for index, img in enumerate(self.master.master.ee_images_list):

                eeid, tlxd, tlyd, brxd, bryd, fdate, ldate, cloud, image = img

                nfdate = datetime(int(fdate[0:4]), int(fdate[5:7]), int(fdate[8:10]))
                ndate_from = datetime(int(date_from[0:4]), int(date_from[5:7]), int(date_from[8:10]))

                nldate = datetime(int(ldate[0:4]), int(ldate[5:7]), int(ldate[8:10]))
                ndate_until = datetime(int(date_until[0:4]), int(date_until[5:7]), int(date_until[8:10]))

                if (tlxd > top_left[0]
                      and tlyd < top_left[1]
                      and brxd < bottom_right[0]
                      and bryd > bottom_right[1]
                      and nfdate >= ndate_from
                      and nldate <= ndate_until
                      and cloud <= cloudiness):
                    print("Found suitable image in database")
                    self.master.master.load_images_on_map(index=index, forced_to_show=True)
                    #self.master.master.find_ee_image(index=index)
                    return

        if not self.is_ee_authenticated:
            print("Authentication required")
            return

        ee_image_thread = threading.Thread(daemon=True,
                                           target=self.get_ee_image_thread,
                                           args=top_left + bottom_right + (date_from, date_until, cloudiness))
        ee_image_thread.start()

    def get_ee_image_new(self, date_from: str, date_until: str, cloudiness: int,
                         forced: bool = False):
        top_left = self.region_polygon.position_list[0]
        bottom_right = self.region_polygon.position_list[2]

        # Common case
        if not forced:
            for index, img in enumerate(self.master.master.ee_images_list):

                eeid, tlxd, tlyd, brxd, bryd, fdate, ldate, cloud, image = img

                nfdate = datetime(int(fdate[0:4]), int(fdate[5:7]), int(fdate[8:10]))
                ndate_from = datetime(int(date_from[0:4]), int(date_from[5:7]), int(date_from[8:10]))

                nldate = datetime(int(ldate[0:4]), int(ldate[5:7]), int(ldate[8:10]))
                ndate_until = datetime(int(date_until[0:4]), int(date_until[5:7]), int(date_until[8:10]))

                if (tlxd > top_left[0]
                      and tlyd < top_left[1]
                      and brxd < bottom_right[0]
                      and bryd > bottom_right[1]
                      and nfdate >= ndate_from
                      and nldate <= ndate_until
                      and cloud <= cloudiness):
                    print("Found suitable image in database")
                    self.master.master.load_images_on_map(index=index, forced_to_show=True)
                    #self.master.master.find_ee_image(index=index)
                    return

        # Required download case
        if not self.is_ee_authenticated:
            print("Authentication required")
            return

        ee_image_thread = threading.Thread(daemon=True,
                                           target=self.get_ee_image_thread,
                                           args=top_left + bottom_right + (date_from, date_until, cloudiness))
        ee_image_thread.start()

    def switch_ee(self):
        self.use_ee_database = not self.use_ee_database
        self.draw_move()

    def add_ee_image(self,
                     eeid: int,
                     position: Tuple[float, float],
                     brposition: Tuple[float, float],
                     image: Image,
                     fdate: datetime,
                     ldate: datetime,
                     cloudiness: int):
        ee_image = CanvasEEImage(self,
                                 eeid=eeid,
                                 position=position,
                                 brposition=brposition,
                                 image=image,
                                 fdate=fdate,
                                 ldate=ldate,
                                 cloudiness=cloudiness)
        ee_image.draw()
        self.canvas_ee_image_list.append(ee_image)
        return ee_image

    def load_ee_images(self, images):
        for eeid, tlxd, tlyd, brxd, bryd, fdate, ldate, cloudiness, image in images:

            pilimage = Image.open(io.BytesIO(image))
            self.add_ee_image(eeid, (tlxd, tlyd), (brxd, bryd), pilimage, fdate, ldate, cloudiness)

    def unload_ee_images(self, images):
        for eeid, tlxd, tlyd, brxd, bryd, fdate, ldate, cloudiness, image in images:
            for index, loaded_image in enumerate(self.canvas_ee_image_list):
                if eeid == loaded_image.eeid:
                    break

            else:  # If there is no such image
                index = -1

            if index > -1:
                self.canvas_ee_image_list.pop(index)


    # === Other stuff ===

    def set_path(self, position_list: list, **kwargs) -> CanvasPath:
        path = CanvasPath(self, position_list, **kwargs)
        path.draw()
        self.canvas_path_list.append(path)
        return path

    def set_polygon(self, position_list: list, **kwargs) -> CanvasPolygon:
        polygon = CanvasPolygon(self, position_list, **kwargs)
        polygon.draw()
        self.canvas_polygon_list.append(polygon)
        return polygon

    def delete(self, map_object: any):
        if isinstance(map_object, (CanvasPath, CanvasPositionMarker, CanvasPolygon)):
            map_object.delete()

    def delete_all_marker(self):
        for i in range(len(self.canvas_marker_list) - 1, -1, -1):
            self.canvas_marker_list[i].delete()
        self.canvas_marker_list = []

    def delete_all_path(self):
        for i in range(len(self.canvas_path_list) - 1, -1, -1):
            self.canvas_path_list[i].delete()
        self.canvas_path_list = []

    def delete_all_polygon(self):
        for i in range(len(self.canvas_polygon_list) - 1, -1, -1):
            self.canvas_polygon_list[i].delete()
        self.canvas_polygon_list = []

    def manage_z_order(self):
        self.canvas.lift("ee_image")
        self.canvas.lift("polygon")
        self.canvas.lift("path")
        self.canvas.lift("marker")
        self.canvas.lift("marker_image")
        self.canvas.lift("corner")
        self.canvas.lift("button")

        # self.canvas.lower("ee_image")
        # self.canvas.lower("polygon")
        # self.canvas.lower("path")
        # self.canvas.lower("marker")
        # self.canvas.lower("marker_image")
        # self.canvas.lower("corner")
        # self.canvas.lower("button")


    # === Map tiles stuff ===

    def pre_cache(self):
        """ single threaded pre-cache tile images in area of self.pre_cache_position """

        last_pre_cache_position = None
        radius = 1
        zoom = round(self.zoom)

        if self.database_path is not None:
            db_connection = sqlite3.connect(self.database_path, timeout=10)
            db_cursor = db_connection.cursor()
        else:
            db_cursor = None

        while self.running:
            if last_pre_cache_position != self.pre_cache_position:
                last_pre_cache_position = self.pre_cache_position
                zoom = round(self.zoom)
                radius = 1

            if last_pre_cache_position is not None and radius <= 8:

                # pre cache top and bottom row
                for x in range(self.pre_cache_position[0] - radius, self.pre_cache_position[0] + radius + 1):
                    if f"{zoom}{x}{self.pre_cache_position[1] + radius}" not in self.tile_image_cache:
                        self.request_image(zoom, x, self.pre_cache_position[1] + radius, db_cursor=db_cursor)
                    if f"{zoom}{x}{self.pre_cache_position[1] - radius}" not in self.tile_image_cache:
                        self.request_image(zoom, x, self.pre_cache_position[1] - radius, db_cursor=db_cursor)

                # pre cache left and right column
                for y in range(self.pre_cache_position[1] - radius, self.pre_cache_position[1] + radius + 1):
                    if f"{zoom}{self.pre_cache_position[0] + radius}{y}" not in self.tile_image_cache:
                        self.request_image(zoom, self.pre_cache_position[0] + radius, y, db_cursor=db_cursor)
                    if f"{zoom}{self.pre_cache_position[0] - radius}{y}" not in self.tile_image_cache:
                        self.request_image(zoom, self.pre_cache_position[0] - radius, y, db_cursor=db_cursor)



                # raise the radius
                radius += 1

            else:
                time.sleep(0.1)

            # 10_000 images = 80 MB RAM-usage
            if len(self.tile_image_cache) > 10_000:  # delete random tiles if cache is too large
                # create list with keys to delete
                keys_to_delete = []
                for key in self.tile_image_cache.keys():
                    if len(self.tile_image_cache) - len(keys_to_delete) > 10_000:
                        keys_to_delete.append(key)

                # delete keys in list so that len(self.tile_image_cache) == 10_000
                for key in keys_to_delete:
                    del self.tile_image_cache[key]

    def request_image(self, zoom: int, x: int, y: int, db_cursor=None) -> ImageTk.PhotoImage:

        # if database is available check first if tile is in database, if not try to use server
        if db_cursor is not None:

            try:
                db_cursor.execute("SELECT t.tile_image FROM tiles t WHERE t.zoom=? AND t.x=? AND t.y=? AND t.server=?;",
                                  (zoom, x, y, self.tile_server))
                result = db_cursor.fetchone()

                if result is not None:
                    image = Image.open(io.BytesIO(result[0]))
                    image_tk = ImageTk.PhotoImage(image)
                    self.tile_image_cache[f"{zoom} {x} {y}"] = image_tk
                    return image_tk
                elif self.use_database_only:
                    return self.empty_tile_image
                else:
                    pass

            except sqlite3.OperationalError:
                if self.use_database_only:
                    return self.empty_tile_image
                else:
                    pass

            except Exception:
                return self.empty_tile_image

        # try to get the tile from the server
        try:
            url = self.tile_server.replace("{x}", str(x)).replace("{y}", str(y)).replace("{z}", str(zoom))

            answer = requests.get(url, stream=True, headers={"User-Agent": "TkinterMapView"})

            # if got status 200 set connection status to online
            # only if current status is offline to prevent blinking
            if answer.status_code == 200 and self.get_connection_status() != "1":
                self.set_connection_status(True)
            image = Image.open(answer.raw)

            if self.database_path is not None and self.autosave:  # insert into database if it is available
                try:
                    db_connection = sqlite3.connect(self.database_path, timeout=10)
                    cursor = db_connection.cursor()

                    # create buffer because we need to save and load the image and to prevent using local drive
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG")
                    insert_tile_cmd = """INSERT INTO tiles (zoom, x, y, server, tile_image) VALUES (?, ?, ?, ?, ?);"""
                    cursor.execute(insert_tile_cmd, (zoom, x, y, self.tile_server, buffer.getvalue()))
                    db_connection.commit()

                except sqlite3.OperationalError as e:
                    print(f"Failed to insert loaded image because of {e}")
                except Exception as e:
                    print("Most probably failed saving: ", e)
                finally:
                    db_connection.close()

            if self.overlay_tile_server is not None:
                url = self.overlay_tile_server.replace("{x}", str(x)).replace("{y}", str(y)).replace("{z}", str(zoom))
                image_overlay = Image.open(requests.get(url, stream=True, headers={"User-Agent": "TkinterMapView"}).raw)
                image = image.convert("RGBA")
                image_overlay = image_overlay.convert("RGBA")

                if image_overlay.size is not (self.tile_size, self.tile_size):
                    image_overlay = image_overlay.resize((self.tile_size, self.tile_size), Image.ANTIALIAS)

                image.paste(image_overlay, (0, 0), image_overlay)

            if self.running:
                image_tk = ImageTk.PhotoImage(image)
            else:
                return self.empty_tile_image

            self.tile_image_cache[f"{zoom} {x} {y}"] = image_tk
            return image_tk

        except PIL.UnidentifiedImageError:  # image does not exist for given coordinates
            # print("Unidentified Image")
            self.tile_image_cache[f"{zoom} {x} {y}"] = self.empty_tile_image
            return self.empty_tile_image

        except requests.exceptions.ConnectionError:
            if self.get_connection_status() != "0":
                self.set_connection_status(False)
            return self.empty_tile_image

        except Exception as e:
            # print("Broad exception: ", e)
            return self.empty_tile_image

    def get_tile_image_from_cache(self, zoom: int, x: int, y: int):
        if f"{zoom} {x} {y}" not in self.tile_image_cache:
            return False
        else:
            return self.tile_image_cache[f"{zoom} {x} {y}"]

    def load_images_background(self):

        if self.database_path is not None:
            db_connection = sqlite3.connect(self.database_path, timeout=10)
            db_cursor = db_connection.cursor()
        else:
            db_cursor = None

        while self.running:
            if len(self.image_load_queue_tasks) > 0:
                # task queue structure: [((zoom, x, y), corresponding canvas tile object), ... ]
                task = self.image_load_queue_tasks.pop()

                zoom = task[0][0]
                x, y = task[0][1], task[0][2]
                canvas_tile = task[1]

                image = self.get_tile_image_from_cache(zoom, x, y)
                if image is False:
                    image = self.request_image(zoom, x, y, db_cursor=db_cursor)
                    if image is None:
                        self.image_load_queue_tasks.append(task)
                        continue

                # result queue structure: [((zoom, x, y), corresponding canvas tile object, tile image), ... ]
                self.image_load_queue_results.append(((zoom, x, y), canvas_tile, image))

            else:
                time.sleep(0.01)

        # if self.database_path is not None:
        #     db_connection.commit()

    def update_canvas_tile_images(self):

        while len(self.image_load_queue_results) > 0 and self.running:
            # result queue structure: [((zoom, x, y), corresponding canvas tile object, tile image), ... ]
            result = self.image_load_queue_results.pop(0)

            zoom, x, y = result[0][0], result[0][1], result[0][2]
            canvas_tile = result[1]
            image = result[2]

            # check if zoom level of result is still up-to-date, otherwise don't update image
            if zoom == round(self.zoom):
                canvas_tile.set_image(image)

        # This function calls itself every 10 ms with tk.after() so that the image updates come
        # from the main GUI thread, because tkinter can only be updated from the main thread.
        if self.running:
            self.after(10, self.update_canvas_tile_images)

    def insert_row(self, insert: int, y_name_position: int):

        for x_pos in range(len(self.canvas_tile_array)):
            tile_name_position = self.canvas_tile_array[x_pos][0].tile_name_position[0], y_name_position

            image = self.get_tile_image_from_cache(round(self.zoom), *tile_name_position)
            if image is False:
                canvas_tile = CanvasTile(self, self.not_loaded_tile_image, tile_name_position)
                self.image_load_queue_tasks.append(((round(self.zoom), *tile_name_position), canvas_tile))
            else:
                canvas_tile = CanvasTile(self, image, tile_name_position)

            canvas_tile.draw()

            self.canvas_tile_array[x_pos].insert(insert, canvas_tile)

    def insert_column(self, insert: int, x_name_position: int):
        canvas_tile_column = []

        for y_pos in range(len(self.canvas_tile_array[0])):
            tile_name_position = x_name_position, self.canvas_tile_array[0][y_pos].tile_name_position[1]

            image = self.get_tile_image_from_cache(round(self.zoom), *tile_name_position)
            if image is False:
                # image is not in image cache, load blank tile and append position to image_load_queue
                canvas_tile = CanvasTile(self, self.not_loaded_tile_image, tile_name_position)
                self.image_load_queue_tasks.append(((round(self.zoom), *tile_name_position), canvas_tile))
            else:
                # image is already in cache
                canvas_tile = CanvasTile(self, image, tile_name_position)

            canvas_tile.draw()

            canvas_tile_column.append(canvas_tile)

        self.canvas_tile_array.insert(insert, canvas_tile_column)

    def draw_initial_array(self):
        self.image_load_queue_tasks = []

        x_tile_range = math.ceil(self.lower_right_tile_pos[0]) - math.floor(self.upper_left_tile_pos[0])
        y_tile_range = math.ceil(self.lower_right_tile_pos[1]) - math.floor(self.upper_left_tile_pos[1])

        # upper left tile name position
        upper_left_x = math.floor(self.upper_left_tile_pos[0])
        upper_left_y = math.floor(self.upper_left_tile_pos[1])

        for x_pos in range(len(self.canvas_tile_array)):
            for y_pos in range(len(self.canvas_tile_array[0])):
                self.canvas_tile_array[x_pos][y_pos].__del__()

        # create tile array with size (x_tile_range x y_tile_range)
        self.canvas_tile_array = []

        for x_pos in range(x_tile_range):
            canvas_tile_column = []

            for y_pos in range(y_tile_range):
                tile_name_position = upper_left_x + x_pos, upper_left_y + y_pos

                image = self.get_tile_image_from_cache(round(self.zoom), *tile_name_position)
                if image is False:
                    # image is not in image cache, load blank tile and append position to image_load_queue
                    canvas_tile = CanvasTile(self, self.not_loaded_tile_image, tile_name_position)
                    self.image_load_queue_tasks.append(((round(self.zoom), *tile_name_position), canvas_tile))
                else:
                    # image is already in cache
                    canvas_tile = CanvasTile(self, image, tile_name_position)
                canvas_tile_column.append(canvas_tile)

            self.canvas_tile_array.append(canvas_tile_column)

        # draw all canvas tiles
        for x_pos in range(len(self.canvas_tile_array)):
            for y_pos in range(len(self.canvas_tile_array[0])):
                self.canvas_tile_array[x_pos][y_pos].draw()

        # draw other objects on canvas
        for marker in self.canvas_marker_list:
            marker.draw()
        for image in self.canvas_ee_image_list:
            image.draw()
        for path in self.canvas_path_list:
            path.draw()
        for polygon in self.canvas_polygon_list:
            polygon.draw()

        # update pre-cache position
        self.pre_cache_position = (round((self.upper_left_tile_pos[0] + self.lower_right_tile_pos[0]) / 2),
                                   round((self.upper_left_tile_pos[1] + self.lower_right_tile_pos[1]) / 2))

    def draw_move(self, called_after_zoom: bool = False):

        if self.canvas_tile_array:

            # insert or delete rows on top
            top_y_name_position = self.canvas_tile_array[0][0].tile_name_position[1]
            top_y_diff = self.upper_left_tile_pos[1] - top_y_name_position
            if top_y_diff <= 0:
                for y_diff in range(1, math.ceil(-top_y_diff) + 1):
                    self.insert_row(insert=0, y_name_position=top_y_name_position - y_diff)
            elif top_y_diff >= 1:
                for y_diff in range(1, math.ceil(top_y_diff)):
                    for x in range(len(self.canvas_tile_array) - 1, -1, -1):
                        if len(self.canvas_tile_array[x]) > 1:
                            self.canvas_tile_array[x][0].delete()
                            del self.canvas_tile_array[x][0]

            # insert or delete columns on left
            left_x_name_position = self.canvas_tile_array[0][0].tile_name_position[0]
            left_x_diff = self.upper_left_tile_pos[0] - left_x_name_position
            if left_x_diff <= 0:
                for x_diff in range(1, math.ceil(-left_x_diff) + 1):
                    self.insert_column(insert=0, x_name_position=left_x_name_position - x_diff)
            elif left_x_diff >= 1:
                for x_diff in range(1, math.ceil(left_x_diff)):
                    if len(self.canvas_tile_array) > 1:
                        for y in range(len(self.canvas_tile_array[0]) - 1, -1, -1):
                            self.canvas_tile_array[0][y].delete()
                            del self.canvas_tile_array[0][y]
                        del self.canvas_tile_array[0]

            # insert or delete rows on bottom
            bottom_y_name_position = self.canvas_tile_array[0][-1].tile_name_position[1]
            bottom_y_diff = self.lower_right_tile_pos[1] - bottom_y_name_position
            if bottom_y_diff >= 1:
                for y_diff in range(1, math.ceil(bottom_y_diff)):
                    self.insert_row(insert=len(self.canvas_tile_array[0]), y_name_position=bottom_y_name_position + y_diff)
            elif bottom_y_diff <= 1:
                for y_diff in range(1, math.ceil(-bottom_y_diff) + 1):
                    for x in range(len(self.canvas_tile_array) - 1, -1, -1):
                        if len(self.canvas_tile_array[x]) > 1:
                            self.canvas_tile_array[x][-1].delete()
                            del self.canvas_tile_array[x][-1]

            # insert or delete columns on right
            right_x_name_position = self.canvas_tile_array[-1][0].tile_name_position[0]
            right_x_diff = self.lower_right_tile_pos[0] - right_x_name_position
            if right_x_diff >= 1:
                for x_diff in range(1, math.ceil(right_x_diff)):
                    self.insert_column(insert=len(self.canvas_tile_array), x_name_position=right_x_name_position + x_diff)
            elif right_x_diff <= 1:
                for x_diff in range(1, math.ceil(-right_x_diff) + 1):
                    if len(self.canvas_tile_array) > 1:
                        for y in range(len(self.canvas_tile_array[-1]) - 1, -1, -1):
                            self.canvas_tile_array[-1][y].delete()
                            del self.canvas_tile_array[-1][y]
                        del self.canvas_tile_array[-1]

            # draw all canvas tiles
            for x_pos in range(len(self.canvas_tile_array)):
                for y_pos in range(len(self.canvas_tile_array[0])):
                    self.canvas_tile_array[x_pos][y_pos].draw()

            # draw other objects on canvas
            for marker in self.canvas_marker_list:
                marker.draw()
            for image in self.canvas_ee_image_list:
                image.draw(zoom=called_after_zoom)
            for path in self.canvas_path_list:
                path.draw(move=not called_after_zoom)
            for polygon in self.canvas_polygon_list:
                polygon.draw(move=not called_after_zoom)
            if self.region_polygon is not None:
                self.region_polygon.draw(move=not called_after_zoom)

            self.initiate_filtering()

            # update pre-cache position
            self.pre_cache_position = (round((self.upper_left_tile_pos[0] + self.lower_right_tile_pos[0]) / 2),
                                       round((self.upper_left_tile_pos[1] + self.lower_right_tile_pos[1]) / 2))

    def get_fit_image_draw(self):
        return self.master.master.is_showing_fit_images

    def initiate_filtering(self, forced=False):
        position = self.get_position()
        if (not (-EE_IMAGE_SHOW_DISTANCE < position[0] - self.last_filter_position[0] < EE_IMAGE_SHOW_DISTANCE
                and -EE_IMAGE_SHOW_DISTANCE < position[1] - self.last_filter_position[1] < EE_IMAGE_SHOW_DISTANCE)
                or forced):
            self.last_filter_position = position[::]
            self.master.master.filter_ee_images(position, EE_IMAGE_SHOW_DISTANCE * 2)

    def draw_zoom(self):

        if self.canvas_tile_array:

            # clear tile image loading queue, so that no old images from other zoom levels get displayed
            self.image_load_queue_tasks = []

            # upper left tile name position
            upper_left_x = math.floor(self.upper_left_tile_pos[0])
            upper_left_y = math.floor(self.upper_left_tile_pos[1])

            for x_pos in range(len(self.canvas_tile_array)):
                for y_pos in range(len(self.canvas_tile_array[0])):

                    tile_name_position = upper_left_x + x_pos, upper_left_y + y_pos

                    image = self.get_tile_image_from_cache(round(self.zoom), *tile_name_position)

                    if image is False:
                        image = self.not_loaded_tile_image
                        # noinspection PyCompatibility
                        self.image_load_queue_tasks.append(((round(self.zoom), *tile_name_position), self.canvas_tile_array[x_pos][y_pos]))

                    self.canvas_tile_array[x_pos][y_pos].set_image_and_position(image, tile_name_position)

            self.pre_cache_position = (round((self.upper_left_tile_pos[0] + self.lower_right_tile_pos[0]) / 2),
                                       round((self.upper_left_tile_pos[1] + self.lower_right_tile_pos[1]) / 2))

            self.draw_move(called_after_zoom=True)

    def mouse_move(self, event):
        # calculate moving difference from last mouse position
        mouse_move_x = self.last_mouse_down_position[0] - event.x
        mouse_move_y = self.last_mouse_down_position[1] - event.y

        # set move velocity for movement fading out
        delta_t = time.time() - self.last_mouse_down_time
        if delta_t == 0:
            self.move_velocity = (0, 0)
        else:
            self.move_velocity = (mouse_move_x / delta_t, mouse_move_y / delta_t)

        # save current mouse position for next move event
        self.last_mouse_down_position = (event.x, event.y)
        self.last_mouse_down_time = time.time()

        # calculate exact tile size of widget
        tile_x_range = self.lower_right_tile_pos[0] - self.upper_left_tile_pos[0]
        tile_y_range = self.lower_right_tile_pos[1] - self.upper_left_tile_pos[1]

        # calculate the movement in tile coordinates
        tile_move_x = (mouse_move_x / self.width) * tile_x_range
        tile_move_y = (mouse_move_y / self.height) * tile_y_range

        # calculate new corner tile positions
        self.lower_right_tile_pos = (self.lower_right_tile_pos[0] + tile_move_x, self.lower_right_tile_pos[1] + tile_move_y)
        self.upper_left_tile_pos = (self.upper_left_tile_pos[0] + tile_move_x, self.upper_left_tile_pos[1] + tile_move_y)

        self.check_map_border_crossing()
        self.draw_move()

    def mouse_click(self, event):
        self.fading_possible = False

        self.mouse_click_position = (event.x, event.y)

        # save mouse position where mouse is pressed down for moving
        self.last_mouse_down_position = (event.x, event.y)
        self.last_mouse_down_time = time.time()

    def mouse_release(self, event):
        self.fading_possible = True
        self.last_move_time = time.time()

        # check if mouse moved after mouse click event
        if self.mouse_click_position == (event.x, event.y):
            # mouse didn't move
            if self.map_click_callback is not None:
                # get decimal coords of current mouse position
                coordinate_mouse_pos = self.convert_canvas_coords_to_decimal_coords(event.x, event.y)
                self.map_click_callback(coordinate_mouse_pos)
        else:
            # mouse was moved, start fading animation
            self.after(1, self.fading_move)

    def fading_move(self):
        delta_t = time.time() - self.last_move_time
        self.last_move_time = time.time()

        # only do fading when at least 10 fps possible and fading is possible (no mouse movement at the moment)
        if delta_t < 0.1 and self.fading_possible is True:

            # calculate fading velocity
            mouse_move_x = self.move_velocity[0] * delta_t
            mouse_move_y = self.move_velocity[1] * delta_t

            # lower the fading velocity
            lowering_factor = 2 ** (-9 * delta_t)
            self.move_velocity = (self.move_velocity[0] * lowering_factor, self.move_velocity[1] * lowering_factor)

            # calculate exact tile size of widget
            tile_x_range = self.lower_right_tile_pos[0] - self.upper_left_tile_pos[0]
            tile_y_range = self.lower_right_tile_pos[1] - self.upper_left_tile_pos[1]

            # calculate the movement in tile coordinates
            tile_move_x = (mouse_move_x / self.width) * tile_x_range
            tile_move_y = (mouse_move_y / self.height) * tile_y_range

            # calculate new corner tile positions
            self.lower_right_tile_pos = (self.lower_right_tile_pos[0] + tile_move_x, self.lower_right_tile_pos[1] + tile_move_y)
            self.upper_left_tile_pos = (self.upper_left_tile_pos[0] + tile_move_x, self.upper_left_tile_pos[1] + tile_move_y)

            self.check_map_border_crossing()
            self.draw_move()

            if abs(self.move_velocity[0]) > 1 or abs(self.move_velocity[1]) > 1:
                if self.running:
                    self.after(1, self.fading_move)

    def set_zoom(self, zoom: int, relative_pointer_x: float = 0.5, relative_pointer_y: float = 0.5):

        mouse_tile_pos_x = self.upper_left_tile_pos[0] + (self.lower_right_tile_pos[0] - self.upper_left_tile_pos[0]) * relative_pointer_x
        mouse_tile_pos_y = self.upper_left_tile_pos[1] + (self.lower_right_tile_pos[1] - self.upper_left_tile_pos[1]) * relative_pointer_y

        current_deg_mouse_position = osm_to_decimal(mouse_tile_pos_x,
                                                    mouse_tile_pos_y,
                                                    round(self.zoom))
        self.zoom = zoom

        if self.zoom > self.max_zoom:
            self.zoom = self.max_zoom
        if self.zoom < self.min_zoom:
            self.zoom = self.min_zoom

        current_tile_mouse_position = decimal_to_osm(*current_deg_mouse_position, round(self.zoom))

        self.upper_left_tile_pos = (current_tile_mouse_position[0] - relative_pointer_x * (self.width / self.tile_size),
                                    current_tile_mouse_position[1] - relative_pointer_y * (self.height / self.tile_size))

        self.lower_right_tile_pos = (current_tile_mouse_position[0] + (1 - relative_pointer_x) * (self.width / self.tile_size),
                                     current_tile_mouse_position[1] + (1 - relative_pointer_y) * (self.height / self.tile_size))

        if round(self.zoom) != round(self.last_zoom):
            self.check_map_border_crossing()
            self.draw_zoom()
            self.last_zoom = round(self.zoom)

    def mouse_zoom(self, event):
        relative_mouse_x = event.x / self.width  # mouse pointer position on map (x=[0..1], y=[0..1])
        relative_mouse_y = event.y / self.height

        if sys.platform == "darwin":
            new_zoom = self.zoom + event.delta * 0.1
        elif sys.platform.startswith("win"):
            new_zoom = self.zoom + int(event.delta * 0.01)
            #print(new_zoom, self.zoom, event.delta)
        elif event.num == 4:
            new_zoom = self.zoom + 1
        elif event.num == 5:
            new_zoom = self.zoom - 1
        else:
            new_zoom = self.zoom + event.delta * 0.1

        self.set_zoom(new_zoom, relative_pointer_x=relative_mouse_x, relative_pointer_y=relative_mouse_y)

    def check_map_border_crossing(self):
        diff_x, diff_y = 0, 0
        if self.upper_left_tile_pos[0] < 0:
            diff_x += 0 - self.upper_left_tile_pos[0]

        if self.upper_left_tile_pos[1] < 0:
            diff_y += 0 - self.upper_left_tile_pos[1]
        if self.lower_right_tile_pos[0] > 2 ** round(self.zoom):
            diff_x -= self.lower_right_tile_pos[0] - (2 ** round(self.zoom))
        if self.lower_right_tile_pos[1] > 2 ** round(self.zoom):
            diff_y -= self.lower_right_tile_pos[1] - (2 ** round(self.zoom))

        self.upper_left_tile_pos = self.upper_left_tile_pos[0] + diff_x, self.upper_left_tile_pos[1] + diff_y
        self.lower_right_tile_pos = self.lower_right_tile_pos[0] + diff_x, self.lower_right_tile_pos[1] + diff_y

    def button_zoom_in(self):
        # zoom into middle of map
        self.set_zoom(self.zoom + 1, relative_pointer_x=0.5, relative_pointer_y=0.5)

    def button_zoom_out(self):
        # zoom out of middle of map
        self.set_zoom(self.zoom - 1, relative_pointer_x=0.5, relative_pointer_y=0.5)

    def button_connection(self):

        self.use_database_only = not self.use_database_only
        if self.use_database_only:
            self.set_connection_status(None)

        else:
            self.button_connection.text = "?"
            self.button_connection.draw()


    # === EE Polygon stuff ===

    def switch_polygon_draw(self):

        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<Button-1>")
        self.canvas.unbind("<ButtonRelease-1>")
        if self.is_regime_polygon:
            self.button_polygon.text = "□"
            self.canvas.bind("<B1-Motion>", self.mouse_move)
            self.canvas.bind("<Button-1>", self.mouse_click)
            self.canvas.bind("<ButtonRelease-1>", self.mouse_release)

        else:
            if self.region_polygon is not None:
                self.region_polygon.delete()
                self.region_polygon = None
            self.button_polygon.text = "■"
            self.canvas.bind("<B1-Motion>", self.mouse_move_polygon)
            self.canvas.bind("<Button-1>", self.mouse_click_polygon)
            self.canvas.bind("<ButtonRelease-1>", self.mouse_release_polygon)

        self.button_polygon.draw()
        self.is_regime_polygon = not self.is_regime_polygon

    def mouse_move_polygon(self, event):

        if self.region_polygon is not None:

            x, y = self.convert_canvas_coords_to_decimal_coords(event.x, event.y)
            # calculate moving difference from last mouse position
            self.region_polygon.position_list[1] = (self.region_polygon.position_list[1][0], y)
            self.region_polygon.position_list[2] = (x, y)
            self.region_polygon.position_list[3] = (x, self.region_polygon.position_list[3][1])
            self.region_polygon.draw()
            self.manage_z_order()

    def mouse_click_polygon(self, event):

        # check if mouse over button
        if self.button_polygon.is_hovered:
            # just clicked on button
            return

        x, y = self.convert_canvas_coords_to_decimal_coords(event.x, event.y)
        
        self.region_polygon = CanvasPolygon(map_widget=self,
                                            position_list=[(x, y),
                                                           (x, y),
                                                           (x, y),
                                                           (x, y)],
                                            )

    def mouse_release_polygon(self, event):
        # top_left[0] > bottom_right[0]
        # top_left[1] < bottom_right[1]
        if self.region_polygon is not None:
            lst = tuple(zip(*self.region_polygon.position_list))
            top_left = (max(lst[0]),
                        min(lst[1]))
            top_right = (min(lst[0]),
                         min(lst[1]))
            bottom_right = (min(lst[0]),
                            max(lst[1]))
            bottom_left = (max(lst[0]),
                           max(lst[1]))

            self.region_polygon.position_list = [top_left,
                                                 top_right,
                                                 bottom_right,
                                                 bottom_left]

        # check if mouse over button
        if self.button_polygon.is_hovered:
            # just clicked on button
            return

        if self.region_polygon is not None:
            self.switch_polygon_draw()


import io
from time import sleep
import threading
from datetime import timedelta
from calendar import monthrange

from PIL import Image, ImageTk

from tkinter import StringVar, IntVar
import customtkinterforked as customtkinter
from tkintermapviewforked import TkinterMapView, utility_functions

from constants import *



# To do list:
#  1. [х] - Fix ee images zoom bug
#  2. [ ] - Download full image collection
#  3. [x] - List of downloaded images
#  4. [?] - Downloading progress bar
#  4.1. [ ] - Try to get progress bar from other libs
#  5. [x] - Don't download image if there already
#            is suitable image in database
#  5.1. [ ] - Consider split images
#  6. [х] - Connection status to top right
#  7. [x] - Data picker
#  8. [x] - Scrollable cloudiness picker
#  8.11. [x] - Fix 0 and 100 cloudiness width bug
#  9. [ ] - Fix blinding white
# 10. [x] - Scrollable in two direction frames
# 11. [x] - Authentication status button
# 12. [x] - Don't show not suitable images
# 13. [ ] - Fix small zoom image scale exception
# 14. [ ] -
# 15. [ ] - Transparency border antialiasing
# 16. [x] - Additional hidden panel with rare options:
# 16.1. [x] - Different sentinel collection picker
# 16.1.1. [ ] - Add sentinels
# 16.2. [x] - Move theme picker
# 16.3. [x] - Scale picker
# 16.4. [x] - Shown images filter option
# 16.5. [ ] -
# 17. [x] - Adequate region picker
# 18. [ ] - Double-click on authentication button bug
# 19. [x] - Hide button instead of load in list of downloaded images when image is loaded
# 20. [x] - Icons on buttons in list
# 21. [ ] - Adjust images when split
# 22. [ ] - Dark theme
# 22.1. [ ] - Custom themes
# 23. [ ] - Package
# 24. [ ] - Fix missing database case
# 25. [x] - Show only related images in list
# 25.1. [ ] - Set images frame at top when there is no images at bottom
# 25.2. [ ] - Sort images when updated
# 25.3. [ ] - Fix it xD
# 26. [ ] - Try splitting into 9, 16 or more
# 27. [ ] - Changing tile server mid-download bug
# 28. [ ] - Just downloaded images doesn't hide, exactly first of the split
# 29. [ ] - Random __del__ exception in PhotoImage

# https://customtkinter.tomschimansky.com/documentation/packaging

customtkinter.set_default_color_theme(os.path.join(DATA_FOLDER, THEME_FILENAME))

os.environ['HTTP_PROXY'] = DEFAULT_PROXY
os.environ['HTTPS_PROXY'] = DEFAULT_PROXY


def change_appearance_mode(new_appearance_mode: str):
    if new_appearance_mode == LIGHT_MODE_NAME:
        customtkinter.set_appearance_mode("Light")
        return
    customtkinter.set_appearance_mode("Dark")


LEFT_FRAME_COUNT = 3


class App(customtkinter.CTk):
    APP_NAME = "ЭРА Спутник"
    WIDTH = 1200
    HEIGHT = 630

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.title(App.APP_NAME)

        self.iconbitmap(os.path.join(DATA_FOLDER, ICON_FILENAME))
        self.geometry(str(App.WIDTH) + "x" + str(App.HEIGHT))
        self.minsize(App.WIDTH, App.HEIGHT)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.createcommand('tk::mac::Quit', self.on_closing)

        self.marker_list = []

        self.ee_images_list = []
        self.last_eeid = [0]
        self.load_ee_images()

        self.selected_top_left_corner = None
        self.selected_bottom_right_corner = None
        self.top_left_marker = None
        self.bottom_right_marker = None
        self.top_left_marker_icon = ImageTk.PhotoImage(Image.open(os.path.join(DATA_FOLDER, CORNER_FILENAME)))
        self.bottom_right_marker_icon = ImageTk.PhotoImage(Image.open(os.path.join(DATA_FOLDER, BR_CORNER_FILENAME)))

        # ============ create three CTkFrames ============

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        FRAMES_WIDTH = 246
        self.frame_left = customtkinter.CTkFrame(
            master=self, corner_radius=0,
            width=FRAMES_WIDTH,
            #, fg_color=("#CCCCCC", "#222222")
        )
        self.frame_left.grid(row=0, column=0, padx=0, pady=0, sticky="nsew")

        self.frame_middle = customtkinter.CTkFrame(master=self, corner_radius=0)
        self.frame_middle.grid(row=0, column=1, rowspan=1, pady=0, padx=0, sticky="nsew")

        self.frame_right = customtkinter.CTkFrame(master=self, width=150, corner_radius=0)
        self.frame_right.grid(row=0, column=2, rowspan=1, pady=0, padx=0, sticky="nsew")

        # ============ frame_left ============

        logo = Image.open(os.path.join(DATA_FOLDER, LOGO_FILENAME))
        ratio = logo.size[1] / logo.size[0]
        self.logo_image = customtkinter.CTkImage(light_image=logo,
                                                 #dark_image=Image.open("logo_dark.png"),
                                                 size=(150, int(150 * ratio))
                                                 )
        self.logo = customtkinter.CTkLabel(master=self.frame_left,
                                           image=self.logo_image,
                                           text="")
        self.logo.grid(row=0, column=0, columnspan=LEFT_FRAME_COUNT, pady=10)

        # Choose frame buttons
        self.main_frame_button = customtkinter.CTkButton(master=self.frame_left, width=0,
                                                         command=lambda: self.choose_frame(0), text="Главная",
                                                         bottom_not_rounded=True)
        self.main_frame_button.grid(row=1, column=0, padx=2, sticky="we")
        self.current_button = self.main_frame_button

        self.images_frame_button = customtkinter.CTkButton(master=self.frame_left, width=0,
                                                           command=lambda: self.choose_frame(1),
                                                           text="Снимки",
                                                           bottom_not_rounded=True)
        self.images_frame_button.grid(row=1, column=1, padx=2, sticky="we")

        self.options_frame_button = customtkinter.CTkButton(master=self.frame_left, width=0,
                                                            command=lambda: self.choose_frame(2), text="Настройки",
                                                            bottom_not_rounded=True)
        self.options_frame_button.grid(row=1, column=2, padx=2, sticky="we")

        # End of frame buttons
        self.frame_left.grid_rowconfigure(2, weight=1)
        #self.frame_left.grid_columnconfigure((0, 2), weight=1)

        # ============ frame_left_main ============
        self.frame_left_main = customtkinter.CTkFrame(
            master=self.frame_left, corner_radius=0, fg_color=("#CCCCCC", "#222222"), width=FRAMES_WIDTH
        )

        self.current_frame = self.frame_left_main
        self.choose_frame(0)

        # for row in range(12):
        #     self.frame_left_main.grid_rowconfigure(row+1, weight=1)

        # ee authentication button
        self.authenticate_button = customtkinter.CTkButton(
            master=self.frame_left_main,
            text="Аутентификация",
            command=self.ee_authenticate)
        self.authenticate_button.grid(row=0, column=0, columnspan=2, pady=(20, 0), padx=(20, 20))

        # Download zone button
        # self.download_button = customtkinter.CTkButton(
        #     master=self.frame_left_main,
        #     text="Скачать регион",
        #     command=self.get_ee_image)
        # self.download_button.grid(row=2, column=0, columnspan=2, pady=(20, 0), padx=(20, 20))

        # New download zone button
        self.download_button = customtkinter.CTkButton(
            master=self.frame_left_main,
            text="Скачать регион",
            command=self.get_ee_image_new)
        self.download_button.grid(row=1, column=0, columnspan=2, pady=(20, 0), padx=(20, 20))
        self.number_of_images_downloading = 0

        self.download_progress_bar = customtkinter.CTkProgressBar(master=self.frame_left_main,
                                                                  mode="indeterminate",
                                                                  indeterminate_speed=2)
        self.download_progress_bar.start()
        # self.download_progress_bar.grid(row=1, column=0, columnspan=2, pady=(20, 0), padx=(20, 20))

        # ee switch
        self.use_ee_switch = customtkinter.CTkSwitch(
            master=self.frame_left_main,
            text="Использовать Earth Engine",
            command=self.switch_ee)
        self.use_ee_switch.grid(row=2, column=0, columnspan=2, pady=(20, 0), padx=(20, 20), )
        self.use_ee_switch.select()

        # Date entries
        self.date_from_var = StringVar(master=None,
                                       value=DEFAULT_DATE_FROM,
                                       name="Date from")
        self.date_from_var.trace_add("write", self.update_ee_image_status)
        self.date_until_var = StringVar(master=None,
                                        value=DEFAULT_DATE_UNTIL,
                                        name="Date until")
        self.date_until_var.trace_add("write", self.update_ee_image_status)

        # New date picker
        self.dates_frame = customtkinter.CTkFrame(master=self.frame_left_main, fg_color="transparent")
        self.dates_frame.grid(row=3, column=0, columnspan=2, pady=(20, 0))

        self.date_label = customtkinter.CTkLabel(master=self.dates_frame,
                                                 text="Дата")
        self.date_label.grid(row=0, column=0, columnspan=2)

        self.date_from_label = customtkinter.CTkLabel(master=self.dates_frame,
                                                      text="С")
        self.date_from_label.grid(row=1, column=0, padx=(20, 20), pady=(20, 0))

        self.date_from_entry = customtkinter.CTkDatePicker(master=self.dates_frame, command=self.update_ee_image_status,
                                                           chosen_date=(date.today() - timedelta(days=monthrange(date.today().year, date.today().month)[1] - 1) ),)
        self.date_from_entry.grid(row=1, column=1, padx=(20, 20), pady=(20, 0))

        self.date_until_label = customtkinter.CTkLabel(master=self.dates_frame,
                                                       text="По")
        self.date_until_label.grid(row=2, column=0, padx=(20, 20), pady=(20, 0))

        self.date_until_entry = customtkinter.CTkDatePicker(master=self.dates_frame, command=self.update_ee_image_status)
        self.date_until_entry.grid(row=2, column=1, padx=(20, 20), pady=(20, 20))

        # Cloudiness
        self.cloudiness_var = IntVar(master=None,
                                     value=50,
                                     name="Cloudiness")
        self.cloudiness_var.trace_add("write", self.update_ee_image_status)

        self.cloudiness_label = customtkinter.CTkLabel(master=self.frame_left_main,
                                                       text="Облачность")
        self.cloudiness_label.grid(row=4, column=0, columnspan=2, padx=(20, 20), pady=(20, 0))
        self.cloudiness_slider = customtkinter.CTkSlider(master=self.frame_left_main,
                                                         orientation="horizontal",
                                                         command=self.print_cloud,
                                                         from_=0,
                                                         to=100,
                                                         number_of_steps=100)
        self.cloudiness_slider.grid(row=5, column=0, padx=(20, 0), pady=(20, 0))
        self.cloudiness_value_label = customtkinter.CTkLabel(master=self.frame_left_main,
                                                             text="50",
                                                             width=22)
        self.cloudiness_value_label.grid(row=5, column=1, padx=(0, 20), pady=(20, 0))

        # Server picker
        self.map_label = customtkinter.CTkLabel(self.frame_left_main, text="Сервер", anchor="w")
        self.map_label.grid(row=6, column=0, columnspan=2, padx=(20, 20), pady=(20, 0))
        self.map_option_menu = customtkinter.CTkOptionMenu(
            self.frame_left_main,
            values=tuple(zip(*servers))[0],
            command=self.change_map)
        self.map_option_menu.grid(row=7, column=0, columnspan=2, padx=(20, 20), pady=(10, 20))

        # ============ images frame ============

        self.frame_left_images = customtkinter.CTkScrollableFrame(
            master=self.frame_left,
            corner_radius=0,
            width=FRAMES_WIDTH,
            fg_color=("#CCCCCC", "#222222"),
            orientation="vertical",
        )

        self.view_icon = customtkinter.CTkImage(light_image=Image.open(os.path.join(DATA_FOLDER, VIEW_ICON_FILENAME)), size=(20, 20))
        self.hide_icon = customtkinter.CTkImage(light_image=Image.open(os.path.join(DATA_FOLDER, HIDE_ICON_FILENAME)), size=(20, 20))
        self.find_icon = customtkinter.CTkImage(light_image=Image.open(os.path.join(DATA_FOLDER, FIND_ICON_FILENAME)), size=(20, 20))
        self.delete_icon = customtkinter.CTkImage(light_image=Image.open(os.path.join(DATA_FOLDER, DELETE_ICON_FILENAME)), size=(20, 20))

        self.is_filtering_required = False
        self.is_filtering_images = False
        self.number_of_shown_images_frames = 0
        self.images_frames = []
        self.render_images_frames()
        # self.filter_thread = threading.Thread(daemon=True, target=self.filter_ee_images_thread)
        # self.filter_thread.start()

        # ============ Options frame =============

        self.frame_left_options = customtkinter.CTkScrollableFrame(
            master=self.frame_left, corner_radius=0, fg_color=("#CCCCCC", "#222222"),
            width=FRAMES_WIDTH,
        )
        self.options_label = customtkinter.CTkLabel(master=self.frame_left_options, text="Настройки изображения")
        self.options_label.grid(row=1, column=0, columnspan=2)

        # Proxy setter
        if not HIDE_PROXY:
            self.proxy_label = customtkinter.CTkLabel(master=self.frame_left_options,
                                                      text="Прокси")
            self.proxy_label.grid(row=0, column=0, sticky="w", padx=(12, 0), pady=12)
            self.proxyvar = StringVar(master=None,
                                      value=DEFAULT_PROXY,
                                      name="Proxy")
            self.proxyvar.trace("w", self.proxy_callback)
            self.proxy_field = customtkinter.CTkEntry(master=self.frame_left_options,
                                                      placeholder_text="Без прокси",
                                                      textvariable=self.proxyvar)
            self.proxy_field.grid(row=0, column=1, sticky="e", padx=(0, 12), pady=12)
            customtkinter.CTkToolTip(widget=self.proxy_field,
                                     message="Прокси\nсервер")

        self.scale_label = customtkinter.CTkLabel(master=self.frame_left_options,
                                                  text="Scale")
        self.scale_label.grid(row=2, column=0, sticky="w", padx=(12, 0), pady=12)
        self.scale_entry = customtkinter.CTkEntry(master=self.frame_left_options)
        self.scale_entry.insert(0, "2")
        self.scale_entry.grid(row=2, column=1, sticky="e", padx=(0, 12), pady=12)

        customtkinter.CTkToolTip(widget=self.scale_entry,
                                 message="Устанавливает качество запрашиваемого с сервера EE "
                                         "изображения (целое число, 1 - максимальное качество)")
        
        self.sentinel_label = customtkinter.CTkLabel(master=self.frame_left_options,
                                                     text="Спутник")
        self.sentinel_label.grid(row=3, column=0, sticky="w", padx=(12, 0), pady=12)
        self.sentinel_entry = customtkinter.CTkOptionMenu(master=self.frame_left_options,
                                                          values=tuple(zip(*collections))[0],
                                                          command=lambda: None,
                                                          )
        self.sentinel_entry.grid(row=3, column=1, sticky="e", padx=(0, 12), pady=12)
        customtkinter.CTkToolTip(widget=self.sentinel_entry,
                                 message="Спутник, с которого запрашиваются изображения")

        self.theme_label = customtkinter.CTkLabel(master=self.frame_left_options, text="Настройки внешнего вида")
        self.theme_label.grid(row=4, column=0, columnspan=2)

        self.appearance_mode_label = customtkinter.CTkLabel(self.frame_left_options, text="Тема", anchor="w")
        self.appearance_mode_label.grid(row=5, column=0, sticky="w", padx=(12, 0), pady=12)
        self.appearance_mode_option_menu = customtkinter.CTkOptionMenu(
            self.frame_left_options,
            values=[LIGHT_MODE_NAME, DARK_MODE_NAME],
            command=change_appearance_mode)
        self.appearance_mode_option_menu.grid(row=5, column=1, sticky="e", padx=(0, 12), pady=12)

        self.is_filtering_images = True
        self.filter_images_label = customtkinter.CTkLabel(self.frame_left_options,
                                                          text="Снимки\nрядом",
                                                          anchor="w", justify="left")
        self.filter_images_label.grid(row=6, column=0, sticky="w", padx=(12, 0), pady=12)
        self.filter_images_switch = customtkinter.CTkSwitch(master=self.frame_left_options,
                                                            command=self.switch_filter_images,
                                                            text="")
        self.filter_images_switch.grid(row=6, column=1, sticky="e", padx=(0, 12), pady=12)
        self.filter_images_switch.select()

        self.is_showing_fit_images = False
        self.fit_images_label = customtkinter.CTkLabel(self.frame_left_options,
                                                       text="Подходящие\nснимки",
                                                       anchor="w", justify="left")
        self.fit_images_label.grid(row=7, column=0, sticky="w", padx=(12, 0), pady=12)
        self.fit_images_switch = customtkinter.CTkSwitch(master=self.frame_left_options,
                                                         command=self.switch_fit_images,
                                                         text="")
        self.fit_images_switch.grid(row=7, column=1, sticky="e", padx=(0, 12), pady=12)

        self.is_forcing_download = False
        self.forcing_label = customtkinter.CTkLabel(self.frame_left_options,
                                                    text="Принуд.\nзагрузка",
                                                    anchor="w", justify="left")
        self.forcing_label.grid(row=8, column=0, sticky="w", padx=(12, 0), pady=12)
        self.forcing_switch = customtkinter.CTkSwitch(master=self.frame_left_options,
                                                      command=self.switch_forcing_download,
                                                      text="")
        self.forcing_switch.grid(row=8, column=1, sticky="e", padx=(0, 12), pady=12)

        # ============ frame_middle ============
        self.frame_middle.grid_rowconfigure(1, weight=1)
        self.frame_middle.grid_rowconfigure(0, weight=0)
        self.frame_middle.grid_columnconfigure(0, weight=1)
        self.frame_middle.grid_columnconfigure(1, weight=0)
        self.frame_middle.grid_columnconfigure(2, weight=1)

        self.map_widget = TkinterMapView(
            self.frame_middle,
            corner_radius=0,
            database_path=DATABASE_PATH,
            search_database_path=SEARCH_DATABASE_PATH,
            ee_database_path=EE_DATABASE_PATH,
            set_connection_status=self.set_connection_status,
            get_connection_status=self.get_connection_status,
            eeid=self.last_eeid,
        )
        self.map_widget.grid(row=1, rowspan=1, column=0, columnspan=3, sticky="nswe", padx=(0, 0), pady=(0, 0))
        self.map_widget.add_right_click_menu_command(label="Загрузить все сохраненные изображения",
                                                     command=self.load_images_on_map)
        self.map_widget.add_right_click_menu_command(label="Выбрать верхний левый угол",
                                                     command=self.select_top_left,
                                                     pass_coords=True)
        self.map_widget.add_right_click_menu_command(label="Выбрать нижний правый угол",
                                                     command=self.select_bottom_right,
                                                     pass_coords=True)
        self.map_widget.set_ee_settings_vars(date_from=self.date_from_entry.get(),
                                             date_until=self.date_until_entry.get(),
                                             cloudiness=int(self.cloudiness_slider.get())
                                             )

        # Old search
        self.entry = customtkinter.CTkEntry(master=self.frame_middle,
                                            placeholder_text="Введите адрес")
        self.entry.grid(row=0, column=0, sticky="we", padx=(12, 0), pady=12)
        self.entry.bind("<Return>", self.search_event)

        self.search_button = customtkinter.CTkButton(master=self.frame_middle,
                                                     text="Поиск", width=90,
                                                     command=self.search_event)
        self.search_button.grid(row=0, column=1, sticky="w", padx=(12, 0), pady=12)

        # ============ frame_right ============
        self.frame_right.grid_rowconfigure(1, weight=1)
        self.frame_right.grid_rowconfigure(0, weight=0)
        self.frame_right.grid_columnconfigure(0, weight=1)
        self.frame_right.grid_columnconfigure(1, weight=0)

        # Connection button
        self.connection_status_button = customtkinter.CTkButton(master=self.frame_right,
                                                                text="", state="disabled",
                                                                corner_radius=10,
                                                                width=15, height=15)
        self.connection_status_button.grid(row=0, column=1, sticky="e", padx=(0, 12), pady=12)

        # New search
        db_connection = sqlite3.connect(SEARCH_DATABASE_PATH)
        db_cursor = db_connection.cursor()
        command = """SELECT i, address FROM locations"""
        db_cursor.execute(command)
        self.address_list = db_cursor.fetchall()
        db_connection.close()
        locations = list(zip(*self.address_list))[1]
        if 0:
            self.address_frame = customtkinter.CTkScrollableFrame(master=self.frame_right,
                                                                  label_text="Сохраненные адреса")
        else:
            self.address_frame = customtkinter.CTkDualScrollableFrame(master=self.frame_right,
                                                                      label_text="Сохраненные адреса")
        self.address_frame.grid(row=1, column=0, columnspan=2, padx=(12, 0), pady=12, sticky="nswe")
        self.address_button_list = []
        for location in locations:
            button = customtkinter.CTkButton(master=self.address_frame,
                                             text=location,
                                             fg_color="transparent",
                                             anchor="w",
                                             text_color=("#000000", "#FFFFFF"),
                                             command=lambda loc=location: self.choose_address(loc)

            )
            button.grid(row=len(self.address_button_list), column=0, sticky="w")
            self.address_button_list.append(button)

        self.frame_left.lift()

        # Set default values
        self.map_widget.set_address("Анапа")
        self.map_option_menu.set(servers[0][0])
        self.appearance_mode_option_menu.set(LIGHT_MODE_NAME)

        # Autoauthentication
        #self.ee_authenticate()

    def choose_frame(self, index):
        self.current_frame.grid_forget()
        self.current_button.configure(fg_color=UNCHOSEN_FOLDER, state="normal")
        for i in range(2):
            self.frame_left.grid_columnconfigure(i, weight=0)

        self.frame_left.grid_columnconfigure(index, weight=1)
        if index == 0:
            self.current_frame = self.frame_left_main
            self.current_button = self.main_frame_button

        elif index == 1:
            self.current_frame = self.frame_left_images
            self.current_button = self.images_frame_button

        elif index == 2:
            self.current_frame = self.frame_left_options
            self.current_button = self.options_frame_button

        self.current_button.configure(fg_color=CHOSEN_FOLDER, state="disabled")
        self.current_frame.grid(row=2, column=0, columnspan=LEFT_FRAME_COUNT, sticky="nswe")

    def update_ee_image_status(self, *args):
        #print(args)
        self.map_widget.set_ee_settings_vars(date_from=self.date_from_entry.get(),
                                             date_until=self.date_until_entry.get(),
                                             cloudiness=int(self.cloudiness_slider.get())
                                             )
        self.map_widget.draw_move()

    def set_connection_status(self, status: bool):
        if self.map_widget.use_database_only:
            self.connection_status_button.configure(#text="x",
                                                    fg_color=UNKNOWN_COLOR)
            return

        if status:
            self.connection_status_button.configure(#text="1",
                                                    fg_color=CONNECTED_COLOR)
            self.map_widget.set_tile_server(self.map_widget.tile_server)

        else:
            self.connection_status_button.configure(#text="0",
                                                    fg_color=DISCONNECTED_COLOR)

    def get_connection_status(self):
        status_color = self.connection_status_button.cget("fg_color")
        if status_color == CONNECTED_COLOR:
            return "1"

        elif status_color == DISCONNECTED_COLOR:
            return "0"

        elif status_color == UNKNOWN_COLOR:
            return "x"

        else:
            return "?"

    def load_ee_images(self):
        db_connection = sqlite3.connect(EE_DATABASE_PATH)
        db_cursor = db_connection.cursor()
        db_cursor.execute("SELECT id, tlxd, tlyd, brxd, bryd, fdate, ldate, cloudiness, image FROM images")
        images = db_cursor.fetchall()

        for eeid, tlxd, tlyd, brxd, bryd, fdate, ldate, cloudiness, image in images:

            self.ee_images_list.append((eeid, tlxd, tlyd, brxd, bryd, fdate, ldate, cloudiness, image))
        self.last_eeid[0] = eeid

    def load_new_ee_images(self):
        eeid = self.ee_images_list[-1][0]

        db_connection = sqlite3.connect(EE_DATABASE_PATH)
        db_cursor = db_connection.cursor()
        db_cursor.execute("SELECT id, tlxd, tlyd, brxd, bryd, fdate, ldate, cloudiness, image FROM images WHERE id>?",
                          (eeid,))
        images = db_cursor.fetchall()

        for eeid, tlxd, tlyd, brxd, bryd, fdate, ldate, cloudiness, image in images:

            self.ee_images_list.append((eeid, tlxd, tlyd, brxd, bryd, fdate, ldate, cloudiness, image))
            self.render_image_frame((eeid, tlxd, tlyd, brxd, bryd, fdate, ldate, cloudiness, image), new=True)
        self.last_eeid[0] = eeid

    def render_images_frames(self):
        for item in self.ee_images_list:
            self.render_image_frame(item)

# 10 12 2 1
    def render_image_frame(self, item: tuple[int, float, float, float, float, "Any", "Any", int, str],
                           new=False):
        eeid, tlxd, tlyd, brxd, bryd, fdate, ldate, cloudiness, image = item

        frame = customtkinter.CTkFrame(master=self.frame_left_images)
        #frame.grid(row=len(self.images_frames), column=0, padx=(10, 10), pady=(10, 10), sticky="nswe")
        frame.is_hidden = True
        frame.position = ((tlxd + brxd)/2, (tlyd + bryd)/2)

        # thumb = ImageTk.PhotoImage(Image.open(io.BytesIO(image)).resize((85, 85)))
        if isinstance(image, Image.Image):
            thumb = customtkinter.CTkImage(image, size=(85, 85))
        else:
            thumb = customtkinter.CTkImage(Image.open(io.BytesIO(image)), size=(85, 85))

        label = customtkinter.CTkLabel(master=frame, justify="left", image=thumb, compound="left",
                                       text=f""" eeid: {eeid}
 Координаты: 
 ({tlxd:2.3f}, {tlyd:2.3f})
 ({brxd:2.3f}, {bryd:2.3f})
 Дата: {ldate}
 Облачность: {cloudiness}""")
        label.grid(row=0, column=0, rowspan=3, padx=(5, 5), pady=(5, 5))

        frame.is_image_hidden = not new
        if frame.is_image_hidden:
            img = self.view_icon

        else:
            img = self.hide_icon

        button = customtkinter.CTkButton(master=frame, text="", width=20,
                                         image=img, compound="left",
                                         command=lambda index=len(self.images_frames): self.load_images_on_map(index))
        button.grid(row=0, column=1, padx=(0, 5), pady=(5, 0))

        customtkinter.CTkToolTip(widget=button, message="Показать/скрыть")
        frame.view_hide_button = button

        button = customtkinter.CTkButton(master=frame, text="", width=20,
                                         image=self.find_icon, compound="left",
                                         command=lambda index=len(self.images_frames): self.find_ee_image(index))
        button.grid(row=1, column=1, padx=(0, 5))
        customtkinter.CTkToolTip(widget=button, message="Найти")

        button = customtkinter.CTkButton(master=frame, text="", width=20,
                                         image=self.delete_icon, compound="left",
                                         command=lambda index=len(self.images_frames): self.delete_ee_image(index))
        button.grid(row=2, column=1, padx=(0, 5), pady=(0, 5))
        customtkinter.CTkToolTip(widget=button, message="Удалить")
        self.images_frames.append(frame)

    def render_new_ee_image(self):
        pass

    def switch_filter_images(self):
        self.is_filtering_images = not self.is_filtering_images
        self.map_widget.initiate_filtering(True)
        self.frame_left_images.set_top()

    def switch_fit_images(self):
        self.is_showing_fit_images = not self.is_showing_fit_images

    def switch_forcing_download(self):
        self.is_forcing_download = not self.is_forcing_download

    def filter_ee_images(self, position, distance):
        if self.is_filtering_images:
            for frame in self.images_frames:
                if (frame.is_hidden
                        and -distance < frame.position[0] - position[0] < distance
                        and -distance < frame.position[1] - position[1] < distance
                        ):
                    frame.grid(row=self.number_of_shown_images_frames, column=0, padx=(10, 10), pady=(10, 10), sticky="nswe")
                    frame.is_hidden = False
                    self.number_of_shown_images_frames += 1

                elif (not frame.is_hidden
                      and not (-distance < frame.position[0] - position[0] < distance
                               and -distance < frame.position[1] - position[1] < distance)
                      ):
                    frame.grid_forget()
                    frame.is_hidden = True
                    self.number_of_shown_images_frames -= 1

        else:
            for index, frame in enumerate(self.images_frames):
                frame.grid(row=index, column=0, padx=(10, 10), pady=(10, 10), sticky="nswe")
                frame.is_hidden = False

            self.number_of_shown_images_frames = len(self.images_frames)

    def load_images_on_map(self, index=None, forced_to_show=False):
        """Shows and hides images on map
           If index is not specified shows all images
           """
        if index is None:
            self.map_widget.load_ee_images(self.ee_images_list)
            return
        if self.images_frames[index].is_image_hidden:
            self.map_widget.load_ee_images(self.ee_images_list[index:index+1])
            self.images_frames[index].view_hide_button.configure(image=self.hide_icon)
        elif not forced_to_show:
            self.map_widget.unload_ee_images(self.ee_images_list[index:index+1])
            self.images_frames[index].view_hide_button.configure(image=self.view_icon)
        else:
            print("Nothing changed ;)")
            return
        self.images_frames[index].is_image_hidden = not self.images_frames[index].is_image_hidden

    def find_ee_image(self, index):
        #print(self.ee_images_list[index])
        self.map_widget.set_position(deg_x=(self.ee_images_list[index][1]+self.ee_images_list[index][3])/2,
                                     deg_y=(self.ee_images_list[index][2]+self.ee_images_list[index][4])/2)
        self.map_widget.initiate_filtering(forced=True)

    def delete_ee_image(self, index):

        dialog = customtkinter.CTkBoolDialog(text="Вы уверены, что хотите удалить снимок?")
        if not dialog.get_input():
            return

        if not self.images_frames[index].is_image_hidden:
            self.map_widget.unload_ee_images(self.ee_images_list[index:index+1])

        try:
            connection = sqlite3.connect(EE_DATABASE_PATH)
            cursor = connection.cursor()

            command = """DELETE FROM images WHERE id = ?"""

            cursor.execute(command, (self.ee_images_list[index][0],))
            connection.commit()
            connection.close()
            self.images_frames[index].grid_forget()

        except Exception as e:
            print("Failed to delete", self.ee_images_list[index])
            print(e)

    def print_cloud(self, *args):
        self.cloudiness_value_label.configure(text=f"{self.cloudiness_slider.get():.0f}")
        self.update_ee_image_status()

    def add_address(self, location, event=None):
        self.address_list.append(location)
        button = customtkinter.CTkButton(master=self.address_frame,
                                         text=location[1],
                                         fg_color="transparent",
                                         anchor="w",
                                         text_color=("#000000", "#FFFFFF"),
                                         command=lambda loc=location[1]: self.choose_address(loc))
        button.grid(row=len(self.address_button_list), column=0, sticky="w")
        self.address_button_list.append(button)

    def select_top_left(self, position):
        self.selected_top_left_corner = position
        if self.top_left_marker is not None:
            self.top_left_marker.delete()

        self.top_left_marker = self.map_widget.set_marker(*self.selected_top_left_corner,
                                                          icon=self.top_left_marker_icon,
                                                          icon_anchor="nw")

    def select_bottom_right(self, position):
        self.selected_bottom_right_corner = position
        if self.bottom_right_marker is not None:
            self.bottom_right_marker.delete()

        self.bottom_right_marker = self.map_widget.set_marker(*self.selected_bottom_right_corner,
                                                              icon=self.bottom_right_marker_icon,
                                                              icon_anchor="se")

    def ee_authenticate(self):
        self.authenticate_button.configure(text="Аутентификация...", state="disabled")
        self.map_widget.ee_authenticate(lambda: self.authenticate_button.configure(text="Аутентифицировано",
                                                                                   state="disabled"),
                                        lambda: self.authenticate_button.configure(text="Аутентификация",
                                                                                   state="normal")
                                        )

    def get_ee_image_depr(self):
        if self.selected_top_left_corner is None or self.selected_bottom_right_corner is None:
            print("Select rectangle first")
            return

        from_date = self.date_from_entry.get()
        until_date = self.date_until_entry.get()
        for date in (from_date, until_date):
            if len(date) != 10 or date.count("-") != 2:
                print("Wrong date format")
                return

        try:
            cloud = int(self.cloudiness_slider.get())

        except ValueError:
            print("Wrong cloud format")
            return

        self.map_widget.get_ee_image_depr(self.selected_top_left_corner, self.selected_bottom_right_corner,
                                     from_date, until_date, cloud, self.last_eeid)

    def get_ee_image_new(self):

        if self.map_widget.region_polygon is None:
            print("Choose region first")
            return

        from_date = self.date_from_entry.get()
        until_date = self.date_until_entry.get()

        for date in (from_date, until_date):
            if len(date) != 10 or date.count("-") != 2:
                print("Wrong date format")
                return

        cloud = int(self.cloudiness_slider.get())

        self.download_button.grid_forget()
        self.download_progress_bar.grid(row=1, column=0, columnspan=2, pady=(20, 0), padx=(20, 20))
        self.map_widget.get_ee_image_new(from_date, until_date, cloud,
                                         forced=self.is_forcing_download)

    def reset_download_button(self):
        self.download_progress_bar.grid_forget()
        self.download_button.grid(row=1, column=0, columnspan=2, pady=(20, 0), padx=(20, 20))
        self.map_widget.region_polygon.delete()
        self.map_widget.region_polygon = None

    def switch_ee(self):
        self.map_widget.switch_ee()

    def print_osm_coordinates(self, position):
        print(round(self.map_widget.zoom), *[int(n) for n in utility_functions.decimal_to_osm(*position, self.map_widget.zoom)])

    def add_to_database(self):
        x, y = tuple(round(n) for n in self.map_widget.upper_left_tile_pos)

    def proxy_callback(self, *args):
        proxy = self.proxy_field.get()
        os.environ['HTTP_PROXY'] = proxy
        os.environ['HTTPS_PROXY'] = proxy

    def choose_address(self, address):
        for index, location in self.address_list:
            if location == address:
                self.map_widget.set_address(index)
                self.map_widget.initiate_filtering(True)
                self.frame_left_images.set_top()
                return

    def get_ee_settings(self):
        pass

    def search_event(self, *args):
        entry = self.entry.get()
        i, address = self.map_widget.set_address(entry)
        if i is None:  # If we can't get address with prompt, try to search punto switched address
            i, address = self.map_widget.set_address(translate(entry))
            if i is None:
                return

        # If found address, append to the list
        self.add_address((i, address))

    def set_marker_event(self):
        current_position = self.map_widget.get_position()
        self.marker_list.append(self.map_widget.set_marker(current_position[0], current_position[1]))

    def clear_marker_event(self):
        for marker in self.marker_list:
            marker.delete()

    def change_map(self, new_map: str):
        for name, url, zoom in servers:
            if new_map == name:
                self.map_widget.set_tile_server(url,
                                                max_zoom=zoom)

    def change_sentinel(self, new_sentinel: str):
        for name, sentinel in collections:
            if new_sentinel == name:
                pass

    def on_closing(self):
        try:
            if not HIDE_PROXY:
                with open(os.path.join(DATA_FOLDER, LAST_PROXY_FILENAME), "w") as f:
                    f.write(self.proxy_field.get())

        except:
            pass

        self.destroy()

    def start(self):
        self.mainloop()

    def get_scale(self):
        try:
            return int(self.scale_entry.get())
        
        except ValueError:
            print("Wrong scale format. Using 2 instead")
            return 2

if __name__ == "__main__":
    before_start()
    app = App()
    app.start()

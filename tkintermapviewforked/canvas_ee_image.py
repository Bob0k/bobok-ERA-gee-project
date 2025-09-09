import tkinter
import sys
from datetime import datetime
from typing import TYPE_CHECKING, Callable
from PIL import ImageTk, Image
if TYPE_CHECKING:
    from .map_widget import TkinterMapView

from .utility_functions import decimal_to_osm, osm_to_decimal


class CanvasEEImage:
    def __init__(self,
                 map_widget: "TkinterMapView",
                 eeid: int,
                 cloudiness: int,
                 position: tuple[float, float],
                 brposition: tuple[float, float],
                 image: Image = None,
                 anchor: str = "nw",
                 fdate: str | datetime = None,
                 ldate: str | datetime = None):

        self.eeid = eeid
        self.map_widget = map_widget

        self.position = position
        self.brposition = brposition

        self.image = image
        self.icon = None
        self.deleted = False
        self.icon_anchor = anchor  # can be center, n, nw, w, sw, s, ew, e, ne

        self.zoom = self.map_widget.zoom

        self.canvas_icon = None
        self.size = None
        self.render_icon()

        # Map settings
        if type(fdate) is str:
            self.fdate = datetime(*tuple(int(d) for d in fdate.split("-")))
        elif type(fdate) is datetime:
            self.fdate = fdate
        else:
            raise Exception("From date must be either str in format YYYY-MM-DD or datetime")

        if type(ldate) is str:
            self.ldate = datetime(*tuple(int(d) for d in ldate.split("-")))
        elif type(ldate) is datetime:
            self.ldate = ldate
        else:
            raise Exception("From date must be either str in format YYYY-MM-DD or datetime")

        self.cloudiness = int(cloudiness)

    def render_icon(self):
        canvas_x0, canvas_y0 = self.get_canvas_pos(self.position)
        canvas_x1, canvas_y1 = self.get_canvas_pos(self.brposition)
        self.size = int(canvas_x1 - canvas_x0), int(canvas_y1 - canvas_y0)

        resized_image = self.image.resize(self.size, resample=0)
        self.icon = ImageTk.PhotoImage(resized_image)
        self.canvas_icon = None

        self.zoom = self.map_widget.zoom

    def delete(self):
        if self in self.map_widget.canvas_ee_image_list:
            self.map_widget.canvas_ee_image_list.remove(self)

        self.map_widget.canvas.delete(self.canvas_icon)

        self.canvas_icon = None
        self.deleted = True
        self.map_widget.canvas.update()

    def set_position(self, deg_x, deg_y):
        self.position = (deg_x, deg_y)
        self.draw()

    def change_icon(self, new_icon: tkinter.PhotoImage):
        if self.icon is None:
            raise AttributeError("CanvasEEImage: marker needs icon image in constructor to change icon image later")
        else:
            self.icon = new_icon
            self.map_widget.canvas.itemconfigure(self.canvas_icon, image=self.icon)

    def get_canvas_pos(self, position):
        tile_position = decimal_to_osm(*position, round(self.map_widget.zoom))

        widget_tile_width = self.map_widget.lower_right_tile_pos[0] - self.map_widget.upper_left_tile_pos[0]
        widget_tile_height = self.map_widget.lower_right_tile_pos[1] - self.map_widget.upper_left_tile_pos[1]

        canvas_pos_x = ((tile_position[0] - self.map_widget.upper_left_tile_pos[0]) / widget_tile_width) * self.map_widget.width
        canvas_pos_y = ((tile_position[1] - self.map_widget.upper_left_tile_pos[1]) / widget_tile_height) * self.map_widget.height

        return canvas_pos_x, canvas_pos_y

    def is_fit_with_map_settings(self):
        is_fdate_fit = self.map_widget.date_from <= self.fdate <= self.map_widget.date_until
        is_ldate_fit = self.map_widget.date_from <= self.ldate <= self.map_widget.date_until
        is_cloudiness_fit = self.cloudiness <= self.map_widget.cloudiness

        # print(self.map_widget.date_from, self.fdate, self.map_widget.date_until, self.map_widget.date_from <= self.fdate <= self.map_widget.date_until)
        return is_fdate_fit and is_ldate_fit and is_cloudiness_fit

    def draw(self, zoom=False, event=None):

        # if not self.is_fit_with_map_settings():
        #     return
        # else:
        #     self.map_widget.canvas.delete(self.canvas_icon)
        #     self.canvas_icon = None


        canvas_pos_x, canvas_pos_y = self.get_canvas_pos(self.position)

        # print(f"canvas_pos_x, canvas_pos_y {canvas_pos_x, canvas_pos_y}")
        # print(f"self.position {self.position}")

        if not self.deleted:
            if self.map_widget.use_ee_database and -self.size[0] - 50 < canvas_pos_x < self.map_widget.width + 50 \
                    and -self.size[1] < canvas_pos_y < self.map_widget.height + 70\
                    and (self.is_fit_with_map_settings() or not self.map_widget.get_fit_image_draw()):

                if self.zoom != self.map_widget.zoom:
                    self.render_icon()

                if self.icon is not None:
                    if self.canvas_icon is None:
                        self.canvas_icon = self.map_widget.canvas.create_image(canvas_pos_x, canvas_pos_y,
                                                                               anchor=self.icon_anchor,
                                                                               image=self.icon,
                                                                               tag="ee_image")
                    else:
                        self.map_widget.canvas.coords(self.canvas_icon, canvas_pos_x, canvas_pos_y)

            else:
                self.map_widget.canvas.delete(self.canvas_icon)
                self.canvas_icon = None

            self.map_widget.manage_z_order()

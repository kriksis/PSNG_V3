#!/usr/bin/env python
#
# Copyright (c) 2015 Serguei Glavatski ( verser  from cnc-club.ru )
# Copyright (c) 2020 Probe Screen NG Developers
# Copyright (c) 2022 Alkabal free fr with different approach
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; If not, see <http://www.gnu.org/licenses/>.

from .base import ProbeScreenBase

import os
import sys

import hal
import hal_glib

from subprocess import Popen, PIPE

import math
import time

class ProbeScreenRotation(ProbeScreenBase):
    # --------------------------
    #
    #  INIT
    #
    # --------------------------
    def __init__(self, halcomp, builder, useropts):
        super(ProbeScreenRotation, self).__init__(halcomp, builder, useropts)

        self.hal_led_auto_rott = self.builder.get_object("hal_led_auto_rott")
        self.spbtn_offs_angle = self.builder.get_object("spbtn_offs_angle")

        self.halcomp.newpin("offs_angle", hal.HAL_FLOAT, hal.HAL_OUT)
        self.spbtn_offs_angle.set_value(self.prefs.getpref("offs_angle", 0.0, float))
        self.halcomp["offs_angle"] = self.spbtn_offs_angle.get_value()

        self.halcomp.newpin("chk_auto_rott", hal.HAL_BIT, hal.HAL_OUT)
        self.chk_auto_rott = self.builder.get_object("chk_auto_rott")
        self.chk_auto_rott.set_active(self.prefs.getpref("chk_auto_rott", False, bool))
        if self.chk_auto_rott.get_active():
            self.halcomp["chk_auto_rott"] = True
            self.hal_led_auto_rott.hal_pin.set(1)
        else:
            self.halcomp["chk_auto_rott"] = False
            self.hal_led_auto_rott.hal_pin.set(0)

    # --------------------------
    #
    # Rotate Buttons
    #
    # --------------------------
    def on_chk_auto_rott_toggled(self, gtkcheckbutton, data=None):
        self.halcomp["chk_auto_rott"] = gtkcheckbutton.get_active()
        self.hal_led_auto_rott.hal_pin.set(gtkcheckbutton.get_active())
        self.prefs.putpref("chk_auto_rott", gtkcheckbutton.get_active(), bool)

    def on_spbtn_offs_angle_key_press_event(self, gtkspinbutton, data=None):
        self.on_common_spbtn_key_press_event("offs_angle", gtkspinbutton, data)

    def on_spbtn_offs_angle_value_changed(self, gtkspinbutton, data=None):
        self.on_common_spbtn_value_changed("offs_angle", gtkspinbutton, data)

    @ProbeScreenBase.ensure_errors_dismissed
    def on_btn_set_angle_released(self, gtkbutton, data=None):
        tooldiameter = float(Popen("halcmd getp halui.tool.diameter", shell=True, stdout=PIPE).stdout.read())

        s = "G10 L2 P0"
        if self.halcomp["set_zero"]:
            s += " X%.4f" % (self.halcomp["offs_x"])
            s += " Y%.4f" % (self.halcomp["offs_y"])
        else:
            self.stat.poll()   # before using some self value from linuxcnc we need to poll
            x = self.stat.position[0]
            y = self.stat.position[1]
            s += " X%.4f" % (x)
            s += " Y%.4f" % (y)
        s += " R%.4f" % (self.spbtn_offs_angle.get_value())
        if self.gcode(s) == -1:
            return
        self.add_history_text("btn_set_angle = %.4f" % (self.spbtn_offs_angle.get_value()))
        #self.vcp_reload()
        #time.sleep(1)


    # Y+Y+
    @ProbeScreenBase.ensure_errors_dismissed
    def on_btn_angle_yp_released(self, gtkbutton, data=None):
        tooldiameter = float(Popen("halcmd getp halui.tool.diameter", shell=True, stdout=PIPE).stdout.read())
        if self.ocode("o<backup_status> call") == -1:
            return
        if self.ocode("o<psng_hook> call [7]") == -1:
            return
        if self.ocode("o<psng_load_var_touch_probe> call") == -1:
            return
        self.stat.poll()   # before using some self value from linuxcnc we need to poll
        xstart = (
            self.stat.position[0]
            - self.stat.g5x_offset[0]
            - self.stat.g92_offset[0]
            - self.stat.tool_offset[0]
        )

        # move Y - clearance_xy
        s = """G91
        G1 Y-%f
        G90""" % (self.halcomp["clearance_xy"])
        if self.gcode(s) == -1:
            return

        # Start psng_yplus.ngc load var fromm hal
        if self.ocode("o<psng_start_yplus_probing> call") == -1:
            return

        # Calculate Y result
        a = self.probed_position_with_offsets()
        ycres = float(a[1]) + (0.5 * tooldiameter)
        if self.halcomp["chk_touch_plate_selected"] == True:
            ycres = float(a[1]) + self.halcomp["tp_XY_thickness"] + (0.5 * tooldiameter)

        # move Z temporary away from probing position
        if self.clearance_z_up() == -1:
            return

        # move X + edge_length
        s = """G91
        G1 X%f
        G90""" % (self.halcomp["edge_length"])
        if self.gcode(s) == -1:
            return

        # move Z to probing position
        if self.clearance_z_down() == -1:
            return

        # Start psng_yplus.ngc load var fromm hal
        if self.ocode("o<psng_start_yplus_probing> call") == -1:
            return

        # Calculate Y result
        a = self.probed_position_with_offsets()
        ypres = float(a[1]) + (0.5 * tooldiameter)
        if self.halcomp["chk_touch_plate_selected"] == True:
            ypres = float(a[1]) + self.halcomp["tp_XY_thickness"] + (0.5 * tooldiameter)
        alfa = math.degrees(math.atan2(ypres - ycres, self.halcomp["edge_length"]))

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "YcYpA",
            yc=ycres,
            yp=ypres,
            a=alfa,
        )

        # move Z temporary away from probing position
        if self.clearance_z_up() == -1:
            return

        # move XY to adj start point
        s = "G1 X%f Y%f" % (xstart, ycres)
        if self.gcode(s) == -1:
            return
        self.rotate_coord_system(alfa, xstart, ycres)
        if self.ocode("o<backup_restore> call [999]") == -1:
            return

    # Y-Y-
    @ProbeScreenBase.ensure_errors_dismissed
    def on_btn_angle_ym_released(self, gtkbutton, data=None):
        tooldiameter = float(Popen("halcmd getp halui.tool.diameter", shell=True, stdout=PIPE).stdout.read())
        if self.ocode("o<backup_status> call") == -1:
            return
        if self.ocode("o<psng_hook> call [7]") == -1:
            return
        if self.ocode("o<psng_load_var_touch_probe> call") == -1:
            return
        self.stat.poll()   # before using some self value from linuxcnc we need to poll
        xstart = (
            self.stat.position[0]
            - self.stat.g5x_offset[0]
            - self.stat.g92_offset[0]
            - self.stat.tool_offset[0]
        )

        # move Y + clearance_xy
        s = """G91
        G1 Y%f
        G90""" % (self.halcomp["clearance_xy"])
        if self.gcode(s) == -1:
            return

        # Start psng_yminus.ngc load var fromm hal
        if self.ocode("o<psng_start_yminus_probing> call") == -1:
            return

        # Calculate Y result
        a = self.probed_position_with_offsets()
        ycres = float(a[1]) - (0.5 * tooldiameter)
        if self.halcomp["chk_touch_plate_selected"] == True:
            ycres = float(a[1]) - self.halcomp["tp_XY_thickness"] - (0.5 * tooldiameter)

        # move Z temporary away from probing position
        if self.clearance_z_up() == -1:
            return

        # move X - edge_length
        s = """G91
        G1 X-%f
        G90""" % (self.halcomp["edge_length"])
        if self.gcode(s) == -1:
            return

        # move Z to probing position
        if self.clearance_z_down() == -1:
            return

        # Start psng_yminus.ngc load var fromm hal
        if self.ocode("o<psng_start_yminus_probing> call") == -1:
            return

        # Calculate Y result
        a = self.probed_position_with_offsets()
        ymres = float(a[1]) - (0.5 * tooldiameter)
        if self.halcomp["chk_touch_plate_selected"] == True:
            ymres = float(a[1]) - self.halcomp["tp_XY_thickness"] - (0.5 * tooldiameter)
        alfa = math.degrees(math.atan2(ycres - ymres, self.halcomp["edge_length"]))

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "YmYcA",
            ym=ymres,
            yc=ycres,
            a=alfa,
        )

        # move Z temporary away from probing position
        if self.clearance_z_up() == -1:
            return

        # move XY to adj start point
        s = "G1 X%f Y%f" % (xstart, ycres)
        if self.gcode(s) == -1:
            return
        self.rotate_coord_system(alfa, xstart, ycres)
        if self.ocode("o<backup_restore> call [999]") == -1:
            return

    # X+X+
    @ProbeScreenBase.ensure_errors_dismissed
    def on_btn_angle_xp_released(self, gtkbutton, data=None):
        tooldiameter = float(Popen("halcmd getp halui.tool.diameter", shell=True, stdout=PIPE).stdout.read())
        if self.ocode("o<backup_status> call") == -1:
            return
        if self.ocode("o<psng_hook> call [7]") == -1:
            return
        if self.ocode("o<psng_load_var_touch_probe> call") == -1:
            return
        self.stat.poll()   # before using some self value from linuxcnc we need to poll
        ystart = (
            self.stat.position[1]
            - self.stat.g5x_offset[1]
            - self.stat.g92_offset[1]
            - self.stat.tool_offset[1]
        )

        # move X - clearance_xy
        s = """G91
        G1 X-%f
        G90""" % (self.halcomp["clearance_xy"])
        if self.gcode(s) == -1:
            return

        # Start psng_xplus.ngc load var fromm hal
        if self.ocode("o<psng_start_xplus_probing> call") == -1:
            return

        # Calculate X result
        a = self.probed_position_with_offsets()
        xcres = float(a[0]) + (0.5 * tooldiameter)
        if self.halcomp["chk_touch_plate_selected"] == True:
            xcres = float(a[0]) + self.halcomp["tp_XY_thickness"] + (0.5 * tooldiameter)

        # move Z temporary away from probing position
        if self.clearance_z_up() == -1:
            return

        # move Y - edge_length
        s = """G91
        G1 Y-%f
        G90""" % (self.halcomp["edge_length"])
        if self.gcode(s) == -1:
            return

        # move Z to probing position
        if self.clearance_z_down() == -1:
            return

        # Start psng_xplus.ngc load var fromm hal
        if self.ocode("o<psng_start_xplus_probing> call") == -1:
            return

        # Calculate X result
        a = self.probed_position_with_offsets()
        xpres = float(a[0]) + (0.5 * tooldiameter)
        if self.halcomp["chk_touch_plate_selected"] == True:
            xpres = float(a[0]) + self.halcomp["tp_XY_thickness"] + (0.5 * tooldiameter)
        alfa = math.degrees(math.atan2(xcres - xpres, self.halcomp["edge_length"]))

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XcXpA",
            xc=xcres,
            xp=xpres,
            a=alfa,
        )

        # move Z temporary away from probing position
        if self.clearance_z_up() == -1:
            return

        # move XY to adj start point
        s = "G1 X%f Y%f" % (xcres, ystart)
        if self.gcode(s) == -1:
            return
        self.rotate_coord_system(alfa, xstart, ycres)
        if self.ocode("o<backup_restore> call [999]") == -1:
            return

    # X-X-
    @ProbeScreenBase.ensure_errors_dismissed
    def on_btn_angle_xm_released(self, gtkbutton, data=None):
        tooldiameter = float(Popen("halcmd getp halui.tool.diameter", shell=True, stdout=PIPE).stdout.read())
        if self.ocode("o<backup_status> call") == -1:
            return
        if self.ocode("o<psng_hook> call [7]") == -1:
            return
        if self.ocode("o<psng_load_var_touch_probe> call") == -1:
            return
        self.stat.poll()   # before using some self value from linuxcnc we need to poll
        ystart = (
            self.stat.position[1]
            - self.stat.g5x_offset[1]
            - self.stat.g92_offset[1]
            - self.stat.tool_offset[1]
        )

        # move X + clearance_xy
        s = """G91
        G1 X%f
        G90""" % (self.halcomp["clearance_xy"])
        if self.gcode(s) == -1:
            return

        # Start psng_xminus.ngc load var fromm hal
        if self.ocode("o<psng_start_xminus_probing> call") == -1:
            return

        # Calculate X result
        a = self.probed_position_with_offsets()
        xcres = float(a[0]) - (0.5 * tooldiameter)
        if self.halcomp["chk_touch_plate_selected"] == True:
            xcres = float(a[0]) - self.halcomp["tp_XY_thickness"] - (0.5 * tooldiameter)

        # move Z temporary away from probing position
        if self.clearance_z_up() == -1:
            return

        # move Y + edge_length
        s = """G91
        G1 Y%f
        G90""" % (self.halcomp["edge_length"])
        if self.gcode(s) == -1:
            return

        # move Z to probing position
        if self.clearance_z_down() == -1:
            return

        # Start psng_xminus.ngc load var fromm hal
        if self.ocode("o<psng_start_xminus_probing> call") == -1:
            return

        # Calculate X result
        a = self.probed_position_with_offsets()
        xmres = float(a[0]) - (0.5 * tooldiameter)
        if self.halcomp["chk_touch_plate_selected"] == True:
            xmres = float(a[0]) - self.halcomp["tp_XY_thickness"] - (0.5 * tooldiameter)
        alfa = math.degrees(math.atan2(xcres - xmres, self.halcomp["edge_length"]))

        self.add_history(
            gtkbutton.get_tooltip_text(),
            "XmXcA",
            xm=xmres,
            xc=xcres,
            a=alfa,
        )

        # move Z temporary away from probing position
        if self.clearance_z_up() == -1:
            return

        # move XY to adj start point
        s = "G1 X%f Y%f" % (xcres, ystart)
        if self.gcode(s) == -1:
            return
        self.rotate_coord_system(alfa, xstart, ycres)
        if self.ocode("o<backup_restore> call [999]") == -1:
            return

    # --------------------------
    #
    # Helper Methods
    #
    # --------------------------
    def rotate_coord_system(self, a=0.0, xstart=0.0, ycres=0.0):

        # move Z temporary away from probing position
        if self.clearance_z_up() == -1:
            return

        # move XY to adj start point
        s = "G1 X%f Y%f" % (xstart, ycres)
        if self.gcode(s) == -1:
            return

        self.spbtn_offs_angle.set_value(a)
        self.add_history(
            gtkbutton.get_tooltip_text(),
            "A",
            a=a,
        )

        if self.chk_auto_rott.get_active():
            s = "G10 L2 P0"
            if self.halcomp["set_zero"]:
                s += " X%s" % (self.halcomp["offs_x"])
                s += " Y%s" % (self.halcomp["offs_y"])
            else:
                self.stat.poll()   # before using some self value from linuxcnc we need to poll
                x = self.stat.position[0]
                y = self.stat.position[1]
                s += " X%s" % (x)
                s += " Y%s" % (y)
            s += " R%s" % (a)
            if self.gcode(s) == -1:
                return
            #self.vcp_reload()
            #time.sleep(1)
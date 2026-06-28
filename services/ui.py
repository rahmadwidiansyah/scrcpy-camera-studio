"""
Scrcpy Camera Studio — UI Layer
Fixes: sidebar collapse, console nav, mirror full layout, app rename.
"""
import customtkinter as ctk
import threading
import os


# ═══════════════════════════════════════════════════════════════
#  DESIGN TOKENS
# ═══════════════════════════════════════════════════════════════
class T:
    BG_0      = "#100C08"
    BG_1      = "#1A1512"
    BG_2      = "#221C18"
    BG_3      = "#2C2420"

    CRIMSON   = "#95122C"
    CRIMSON_H = "#B01535"
    ORANGE    = "#CA3F16"
    ORANGE_H  = "#E04D1E"
    AMBER     = "#FF9408"
    AMBER_H   = "#FFB040"

    GREEN     = "#2ECC71"
    RED       = "#E74C3C"
    YELLOW    = "#F39C12"

    TEXT_0    = "#F5F5F5"
    TEXT_1    = "#B8B8B8"
    TEXT_2    = "#6E6E6E"

    BORDER    = "#2E2520"
    BORDER_L  = "#3D3028"

    R_SM      = 6
    R_MD      = 10

    FONT      = "Inter"
    MONO      = "Consolas"

    # Sidebar widths
    SIDEBAR_W  = 185   # expanded
    SIDEBAR_C  = 48    # collapsed (icon only)


# ═══════════════════════════════════════════════════════════════
#  WIDGET FACTORIES
# ═══════════════════════════════════════════════════════════════
def make_label(parent, text, size=12, weight="normal", color=T.TEXT_1, anchor="w", **kw):
    return ctk.CTkLabel(
        parent, text=text, anchor=anchor,
        font=(T.FONT, size, weight), text_color=color, **kw
    )

def make_divider(parent, **kw):
    return ctk.CTkFrame(parent, height=1, fg_color=T.BORDER, **kw)

def make_card(parent, **kw):
    return ctk.CTkFrame(
        parent, fg_color=T.BG_1, corner_radius=T.R_MD,
        border_width=1, border_color=T.BORDER, **kw
    )

def themed_optmenu(parent, values, command=None, variable=None, **kw):
    opts = dict(
        values=values,
        font=(T.FONT, 12),
        dropdown_font=(T.FONT, 12),
        fg_color=T.BG_2,
        button_color=T.BG_3,
        button_hover_color=T.BORDER_L,
        text_color=T.TEXT_0,
        dropdown_fg_color=T.BG_1,
        dropdown_hover_color=T.BG_3,
        dropdown_text_color=T.TEXT_0,
        corner_radius=T.R_SM,
        height=34,
    )
    opts.update(kw)
    if variable:
        opts["variable"] = variable
    if command:
        opts["command"] = command
    return ctk.CTkOptionMenu(parent, **opts)

def themed_segmented(parent, values, variable, command=None):
    return ctk.CTkSegmentedButton(
        parent, values=values, variable=variable, command=command,
        font=(T.FONT, 12, "bold"),
        selected_color=T.CRIMSON, selected_hover_color=T.CRIMSON_H,
        unselected_color=T.BG_2, unselected_hover_color=T.BG_3,
        text_color=T.TEXT_0, corner_radius=T.R_SM, height=34,
    )

def primary_btn(parent, text, command, width=140, **kw):
    return ctk.CTkButton(
        parent, text=text, command=command, width=width, height=36,
        font=(T.FONT, 13, "bold"), corner_radius=T.R_SM,
        fg_color=T.AMBER, hover_color=T.AMBER_H, text_color="#1A0A00", **kw
    )

def secondary_btn(parent, text, command, width=100, **kw):
    return ctk.CTkButton(
        parent, text=text, command=command, width=width, height=36,
        font=(T.FONT, 13, "bold"), corner_radius=T.R_SM,
        fg_color=T.CRIMSON, hover_color=T.CRIMSON_H, text_color=T.TEXT_0, **kw
    )

def ghost_btn(parent, text, command, width=90, height=30, **kw):
    return ctk.CTkButton(
        parent, text=text, command=command, width=width, height=height,
        font=(T.FONT, 11), corner_radius=T.R_SM,
        fg_color=T.BG_2, hover_color=T.BG_3, text_color=T.TEXT_1, **kw
    )


def widget_is_alive(widget):
    """Return True when a Tk widget still exists and can be safely updated."""
    if widget is None:
        return False
    try:
        if hasattr(widget, "winfo_exists"):
            return bool(widget.winfo_exists())
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
#  TOOLTIP
# ═══════════════════════════════════════════════════════════════
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>",    self.show_tip)
        widget.bind("<Leave>",    self.hide_tip)
        widget.bind("<Button-1>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 8
        y = self.widget.winfo_rooty() + 4
        self.tip_window = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        ctk.CTkLabel(
            tw, text=self.text, justify="left",
            fg_color=T.BG_1, text_color=T.TEXT_1, corner_radius=T.R_SM,
            padx=8, pady=4, font=(T.FONT, 10),
            border_width=1, border_color=T.BORDER,
        ).pack(ipadx=1)

    def hide_tip(self, event=None):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()


# ═══════════════════════════════════════════════════════════════
#  DEVICE SELECTOR WIDGET
# ═══════════════════════════════════════════════════════════════
class DeviceSelector(ctk.CTkFrame):
    NONE_LABEL = "— No device —"

    def __init__(self, parent, label: str, on_change=None, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.grid_columnconfigure(1, weight=1)
        self._on_change = on_change
        self._serial_map: dict = {}

        make_label(self, label, size=11, color=T.TEXT_2).grid(row=0, column=0, sticky="w", padx=(0, 12))

        self._var = ctk.StringVar(value=self.NONE_LABEL)
        self._menu = themed_optmenu(self, [self.NONE_LABEL], variable=self._var, command=self._on_select)
        self._menu.grid(row=0, column=1, sticky="ew")

        self._dot = make_label(self, "●", size=11, color=T.TEXT_2)
        self._dot.grid(row=0, column=2, padx=(8, 0))

    def update_devices(self, devices, selected_serial: str = ""):
        self._serial_map = {}
        options = []
        for dev in devices:
            if dev.status == "device":
                lbl = dev.display_label
                self._serial_map[lbl] = dev.serial
                options.append(lbl)

        if not options:
            self._menu.configure(values=[self.NONE_LABEL])
            self._var.set(self.NONE_LABEL)
            self._dot.configure(text_color=T.TEXT_2)
            return

        self._menu.configure(values=options)
        target_lbl = None
        for lbl, ser in self._serial_map.items():
            if ser == selected_serial:
                target_lbl = lbl
                break

        if target_lbl:
            self._var.set(target_lbl)
        elif self._var.get() not in self._serial_map:
            target_lbl = options[0]
            self._var.set(target_lbl)
            serial = self._serial_map.get(target_lbl, "")
            if self._on_change and serial:
                self._on_change(serial)
        self._update_dot()

    def _on_select(self, lbl: str):
        self._update_dot()
        serial = self._serial_map.get(lbl, "")
        if self._on_change:
            self._on_change(serial)

    def _update_dot(self):
        lbl = self._var.get()
        if lbl == self.NONE_LABEL:
            self._dot.configure(text_color=T.TEXT_2)
        elif "[WiFi" in lbl:
            self._dot.configure(text_color=T.YELLOW)
        else:
            self._dot.configure(text_color=T.GREEN)

    def get_serial(self) -> str:
        return self._serial_map.get(self._var.get(), "")

    def set_serial(self, serial: str):
        for lbl, ser in self._serial_map.items():
            if ser == serial:
                self._var.set(lbl)
                self._update_dot()
                return


# ═══════════════════════════════════════════════════════════════
#  SECTION / FIELD HELPERS
# ═══════════════════════════════════════════════════════════════
def _section_header(parent, text, row):
    f = ctk.CTkFrame(parent, fg_color="transparent")
    f.grid(row=row, column=0, columnspan=99, sticky="ew", pady=(10, 0))
    make_label(f, text.upper(), size=10, weight="bold", color=T.TEXT_2).pack(side="left", padx=4)
    ctk.CTkFrame(f, height=1, fg_color=T.BORDER).pack(side="left", fill="x", expand=True, padx=(8, 0))

def _card_field(card, label, widget, row, col, colspan=1):
    make_label(card, label, size=11, color=T.TEXT_2).grid(
        row=row, column=col, columnspan=colspan, sticky="w", padx=16, pady=(12, 2)
    )
    widget.grid(row=row + 1, column=col, columnspan=colspan, sticky="ew", padx=16, pady=(0, 12))


def _build_screenshot_row(card, row, on_change=None):
    make_label(card, "Screenshot Path", size=11, color=T.TEXT_2).grid(
        row=row, column=0, columnspan=2, sticky="w", padx=16, pady=(12, 2)
    )
    path_row = ctk.CTkFrame(card, fg_color="transparent")
    path_row.grid(row=row + 1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))
    path_row.grid_columnconfigure(0, weight=1)

    var = ctk.StringVar()
    entry = ctk.CTkEntry(
        path_row, textvariable=var,
        font=(T.MONO, 11), fg_color=T.BG_2, text_color=T.TEXT_0,
        border_color=T.BORDER, border_width=1, corner_radius=T.R_SM, height=34,
        placeholder_text="Default: ~/Pictures/scrcpy_studio",
        placeholder_text_color=T.TEXT_2,
    )
    entry.grid(row=0, column=0, sticky="ew")

    def browse():
        from tkinter import filedialog
        path = filedialog.askdirectory(title="Select Screenshot Directory")
        if path:
            var.set(path)
            if on_change:
                on_change(path)

    browse_btn = ctk.CTkButton(
        path_row, text="…", width=40, height=34,
        font=(T.FONT, 13, "bold"), fg_color=T.BG_3, hover_color=T.BORDER_L,
        text_color=T.TEXT_1, corner_radius=T.R_SM, command=browse,
    )
    browse_btn.grid(row=0, column=1, padx=(8, 0))
    card._ss_var    = var
    card._ss_entry  = entry
    card._ss_browse = browse_btn


# ═══════════════════════════════════════════════════════════════
#  MAIN APPLICATION UI
# ═══════════════════════════════════════════════════════════════
class CameraStudioUI(ctk.CTk):

    APP_NAME = "Scrcpy Camera Studio"

    def report_callback_exception(self, exc, val, tb):
        """Override Tk callback exception handler — always log full traceback."""
        import traceback
        import logging
        tb_str = "".join(traceback.format_exception(exc, val, tb))
        # Write to console so it's always visible even if logger isn't set up yet
        print("[CameraStudio] Uncaught exception in GUI callback:\n" + tb_str)
        try:
            logging.getLogger("CameraStudio.exception").error(
                "Uncaught exception in GUI callback\n" + tb_str
            )
        except Exception:
            pass
        try:
            self.append_log("[ERROR] GUI Callback Exception — see console/log for traceback")
            self.append_log(tb_str.strip().splitlines()[-1] if tb_str.strip() else str(val))
        except Exception:
            pass

    # ── init ─────────────────────────────────────────────────
    def __init__(self):
        super().__init__()
        from config.version import current_version
        from config.config import Config

        font_path = os.path.join(
            Config.APP_DIR, "icon", "lineicons-5.1-free",
            "free-solid-fonts", "lineicons-free-solid.ttf"
        )
        if os.path.exists(font_path):
            ctk.FontManager.load_font(font_path)

        self.current_version = current_version
        self.title(f"{self.APP_NAME}  v{current_version}")
        self.geometry("1060x700")
        self.minsize(860, 580)
        self._set_window_icon(self)
        ctk.set_appearance_mode("Dark")
        self.configure(fg_color=T.BG_0)

        # State
        self.start_callback          = None
        self.stop_callback           = None
        self.setting_change_callback = None
        self.install_callback        = None
        self.status_labels           = {}
        self.device_rows             = []
        self.camera_options          = []
        self._scrcpy_running_ui      = False
        self._ui_thread_id           = threading.get_ident()
        self.update_result           = None
        self._sidebar_expanded       = True
        self._active_nav             = "camera"
        self._prev_statuses          = {"camera": False, "mirror": False}
        self._all_devices            = []
        # legacy compat
        self.var_target_dev          = ctk.StringVar()

        self._setup_ui()

    # ── external wiring ──────────────────────────────────────
    def set_callbacks(self, start_cb, stop_cb, setting_change_cb, install_cb):
        self.start_callback          = start_cb
        self.stop_callback           = stop_cb
        self.setting_change_callback = setting_change_cb
        self.install_callback        = install_cb

    def apply_theme(self, theme_name):
        if theme_name:
            ctk.set_appearance_mode(theme_name)

    # ── settings → UI ─────────────────────────────────────────
    def load_settings_to_ui(self, settings_data):
        self.current_settings = settings_data
        cam_id = settings_data.get("last_camera", "")
        self.opt_cam.set(f"Camera {cam_id}" if cam_id else "Auto")
        self.opt_res.set(str(settings_data.get("resolution", "1080")))
        self.opt_fps.set(str(settings_data.get("fps", 30)))
        self.opt_bit.set(str(settings_data.get("bitrate", "8M")))
        if hasattr(self, "var_ar"):
            self.var_ar.set(str(settings_data.get("aspect_ratio", "Auto")))
        icon_up    = chr(57366)
        icon_right = chr(57364)
        icon_down  = chr(57361)
        icon_left  = chr(57362)
        rot_val = settings_data.get("rotate", 0)
        rev_map = {
            0: icon_up, 90: icon_right, 180: icon_down, 270: icon_left,
            "0": icon_up, "90": icon_right, "180": icon_down, "270": icon_left
        }
        if hasattr(self, "var_rot"):
            self.var_rot.set(rev_map.get(rot_val, icon_up))
        self.opt_preview.set(str(settings_data.get("preview_mode", "Normal Window")))
        self.opt_audio.set(str(settings_data.get("audio_source", "Playback")))
        self.opt_mirror_res.set(str(settings_data.get("resolution", "Auto")))
        if hasattr(self, "var_mirror"):
            self.var_mirror.set("Mirrored" if settings_data.get("mirror", False) else "Normal")
        if hasattr(self, "btn_mirror") or hasattr(self, "btn_rotate"):
            self._refresh_camera_transform_buttons()
        if hasattr(self, "var_screenshot_path"):
            self.var_screenshot_path.set(settings_data.get("screenshot_path", ""))
        if hasattr(self, "opt_mirror_res"):
            self.opt_mirror_res.set(str(settings_data.get("mirror_resolution", settings_data.get("resolution", "Auto"))))
        if hasattr(self, "opt_mirror_bit"):
            self.opt_mirror_bit.set(str(settings_data.get("mirror_bitrate", settings_data.get("bitrate", "Auto"))))

    def _refresh_camera_transform_buttons(self):
        mirror = getattr(self, "current_settings", {}).get("mirror", False)
        rotate = getattr(self, "current_settings", {}).get("rotate", 0) or 0

        self.btn_mirror.configure(
            text=f"🪞 {'Mirrored' if mirror else 'Mirror'}",
            fg_color=T.GREEN if mirror else T.BG_2,
            hover_color=T.GREEN if mirror else T.BG_3,
        )

        self.btn_rotate.configure(
            text=f"↻ {rotate}°",
        )

    def _on_camera_mirror_toggle(self):
        mirror = not getattr(self, "current_settings", {}).get("mirror", False)
        self._on_setting_change("mirror", mirror)
        self._refresh_camera_transform_buttons()

    def _on_camera_rotate_click(self):
        rotate = (getattr(self, "current_settings", {}).get("rotate", 0) or 0) + 90
        rotate = rotate % 360
        self._on_setting_change("rotate", rotate)
        self._refresh_camera_transform_buttons()

    # ── log ──────────────────────────────────────────────────
    def append_log(self, message):
        if threading.get_ident() != self._ui_thread_id:
            try:
                self.after(0, lambda: self.append_log(message))
            except Exception:
                pass
            return
        tag = "error" if self._is_error_log(message) else "normal"
        self.txt_log.configure(state="normal")
        try:
            self.txt_log.insert("end", message + "\n", tag)
        except Exception:
            self.txt_log.insert("end", message + "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _is_error_log(self, message):
        lowered = message.lower()
        return any(k in lowered for k in ("[error]", "error:", "gagal", "failed"))

    def _ensure_log_textbox(self):
        """No-op: txt_log is always created in _build_console_page."""
        pass

    # ═══════════════════════════════════════════════════════════
    #  MASTER LAYOUT
    # ═══════════════════════════════════════════════════════════
    def _setup_ui(self):
        # row 0 = main content; row 1 = status bar
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=0)   # sidebar — fixed
        self.grid_columnconfigure(1, weight=1)   # content — expands

        self._build_sidebar()
        self._build_content_area()
        self._build_statusbar()

    # ═══════════════════════════════════════════════════════════
    #  SIDEBAR  (fixed width; scrollable; collapse hides labels)
    # ═══════════════════════════════════════════════════════════
    def _build_sidebar(self):
        # Outer frame — fixed width, never shrinks
        self.sidebar = ctk.CTkFrame(
            self, fg_color=T.BG_1, corner_radius=0, width=T.SIDEBAR_W
        )
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsw")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(0, weight=1)
        self.sidebar.grid_columnconfigure(0, weight=1)

        # ── SCROLLABLE CONTAINER (entire sidebar content) ──────────────
        self._sidebar_scroll = ctk.CTkScrollableFrame(
            self.sidebar,
            fg_color="transparent",
            scrollbar_button_color=T.BG_3,
            scrollbar_button_hover_color=T.BORDER_L,
            corner_radius=0,
        )
        self._sidebar_scroll.grid(row=0, column=0, sticky="nsew")
        self._sidebar_scroll.grid_columnconfigure(0, weight=1)

        scroll = self._sidebar_scroll   # shorthand

        # Brand row
        brand_row = ctk.CTkFrame(scroll, fg_color="transparent")
        brand_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(14, 6))

        # Toggle button (always visible — doubles as logo)
        self._btn_collapse_icon = ctk.CTkButton(
            brand_row, text="◉",
            width=32, height=32,
            font=(T.FONT, 16, "bold"),
            fg_color="transparent", hover_color=T.BG_3,
            text_color=T.AMBER, corner_radius=T.R_SM,
            command=self._toggle_sidebar,
        )
        self._btn_collapse_icon.pack(side="left")

        self._logo_text_lbl = make_label(
            brand_row, f" {self.APP_NAME}", size=13, weight="bold", color=T.TEXT_0
        )
        self._logo_text_lbl.pack(side="left")

        make_divider(scroll).grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 4))

        # Nav buttons
        nav_items = [
            ("camera",  "📷", "Camera"),
            ("mirror",  "🖥",  "Screen Mirror"),
            ("devices", "📱", "Devices"),
            ("console", "📋", "Console"),
        ]
        self._nav_buttons = {}
        for i, (key, icon, label) in enumerate(nav_items):
            btn = self._make_nav_btn(
                scroll, icon, label,
                command=lambda k=key: self._switch_nav(k),
                active=(key == self._active_nav),
            )
            btn.grid(row=2 + i, column=0, sticky="ew", padx=8, pady=2)
            self._nav_buttons[key] = btn

        # Spacer — pushes dep section down (but scrollable)
        self._nav_spacer = ctk.CTkFrame(scroll, fg_color="transparent", height=2)
        self._nav_spacer.grid(row=6, column=0, sticky="ew")

        make_divider(scroll).grid(row=7, column=0, sticky="ew", padx=10, pady=(4, 4))

        # Install button — shown via show_installer_flow(), NOT packed yet
        self.btn_install = ctk.CTkButton(
            scroll, text="⚠  Install",
            font=(T.FONT, 11, "bold"), height=34,
            corner_radius=T.R_SM, fg_color=T.ORANGE, hover_color=T.ORANGE_H,
            text_color=T.TEXT_0, command=self._on_install_clicked,
        )
        # Will be placed at row=8 when shown

        # Dependency status section
        self._dep_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self._dep_frame.grid(row=9, column=0, sticky="ew", padx=10, pady=(0, 8))
        self._dep_frame.grid_columnconfigure(0, weight=1)

        self._dep_lbl_header = make_label(
            self._dep_frame, "Dependencies", size=10, color=T.TEXT_2
        )
        self._dep_lbl_header.grid(row=0, column=0, sticky="w", padx=2, pady=(0, 3))

        # Dependency dots in a 2×2 grid for compactness
        self._dep_dot_frame = ctk.CTkFrame(self._dep_frame, fg_color="transparent")
        self._dep_dot_frame.grid(row=1, column=0, sticky="ew")
        self._dep_dot_frame.grid_columnconfigure((0, 1), weight=1)

        self.status_labels = {}
        dep_positions = [("adb", 0, 0), ("scrcpy", 0, 1), ("SDL2", 1, 0), ("ffmpeg", 1, 1)]
        for dep, r, c in dep_positions:
            cell = ctk.CTkFrame(self._dep_dot_frame, fg_color="transparent")
            cell.grid(row=r, column=c, sticky="w", padx=2, pady=1)
            dot = make_label(cell, "●", size=9, color=T.YELLOW, width=14)
            dot.pack(side="left")
            lbl = make_label(cell, dep.upper(), size=10, color=T.TEXT_2)
            lbl.pack(side="left")
            self.status_labels[dep] = (dot, lbl)


    def _make_nav_btn(self, parent, icon, label, command, active=False):
        """Create a nav button that respects collapsed/expanded state."""
        btn = ctk.CTkButton(
            parent,
            text=f"  {icon}  {label}",
            anchor="w",
            width=T.SIDEBAR_W - 16,
            height=36,
            corner_radius=T.R_SM,
            font=(T.FONT, 13),
            fg_color=T.CRIMSON if active else "transparent",
            hover_color=T.BG_3,
            text_color=T.TEXT_0 if active else T.TEXT_1,
            border_spacing=6,
            command=command,
        )
        btn._nav_icon  = icon
        btn._nav_label = label
        return btn

    def _set_nav_active(self, key: str):
        for k, btn in self._nav_buttons.items():
            active = (k == key)
            btn.configure(
                fg_color=T.CRIMSON if active else "transparent",
                text_color=T.TEXT_0 if active else T.TEXT_1,
            )

    def _toggle_sidebar(self):
        self._sidebar_expanded = not self._sidebar_expanded
        scroll = self._sidebar_scroll
        if self._sidebar_expanded:
            self.sidebar.configure(width=T.SIDEBAR_W)
            self._logo_text_lbl.configure(text=f" {self.APP_NAME}")
            for btn in self._nav_buttons.values():
                btn.configure(
                    text=f"  {btn._nav_icon}  {btn._nav_label}",
                    width=T.SIDEBAR_W - 16,
                )
            # Show dep section
            self._dep_frame.grid(row=9, column=0, sticky="ew", padx=10, pady=(0, 8))
            self._dep_lbl_header.grid(row=0, column=0, sticky="w", padx=2, pady=(0, 3))
            self._dep_dot_frame.grid(row=1, column=0, sticky="ew")
            self._btn_collapse_icon.configure(text="\u25c9")
        else:
            self.sidebar.configure(width=T.SIDEBAR_C)
            self._logo_text_lbl.configure(text="")
            for btn in self._nav_buttons.values():
                btn.configure(
                    text=f"  {btn._nav_icon}",
                    width=T.SIDEBAR_C - 8,
                )
            # Hide dep section when collapsed
            self._dep_frame.grid_remove()
            self._btn_collapse_icon.configure(text="\u25ba")

    # ═══════════════════════════════════════════════════════════
    #  CONTENT AREA
    # ═══════════════════════════════════════════════════════════
    def _build_content_area(self):
        self.content_area = ctk.CTkFrame(self, fg_color="transparent")
        self.content_area.grid(row=0, column=1, sticky="nsew")
        self.content_area.grid_rowconfigure(1, weight=1)
        self.content_area.grid_columnconfigure(0, weight=1)

        self._build_toolbar()

        self._pages = {}
        builders = {
            "camera":  self._build_camera_page,
            "mirror":  self._build_mirror_page,
            "devices": self._build_devices_page,
            "console": self._build_console_page,
        }
        for key, builder in builders.items():
            page = ctk.CTkFrame(self.content_area, fg_color="transparent")
            page.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 0))
            # NOTE: each page builder is responsible for configuring its own
            # grid_rowconfigure / grid_columnconfigure weights.
            page.grid_columnconfigure(0, weight=1)
            builder(page)
            self._pages[key] = page

        self._switch_nav("camera")

    # ═══════════════════════════════════════════════════════════
    #  TOOLBAR
    # ═══════════════════════════════════════════════════════════
    def _build_toolbar(self):
        toolbar = ctk.CTkFrame(
            self.content_area, fg_color=T.BG_1, corner_radius=0, height=56,
        )
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.grid_columnconfigure(1, weight=1)
        toolbar.grid_propagate(False)

        self._toolbar_title = make_label(toolbar, "Camera", size=15, weight="bold", color=T.TEXT_0)
        self._toolbar_title.grid(row=0, column=0, sticky="w", padx=20, pady=12)

        pill = ctk.CTkFrame(toolbar, fg_color=T.BG_2, corner_radius=20)
        pill.grid(row=0, column=1, sticky="w", padx=8)
        self._status_dot  = make_label(pill, "●", size=10, color=T.RED)
        self._status_dot.pack(side="left", padx=(8, 2), pady=4)
        self._status_text = make_label(pill, "Stopped", size=11, color=T.TEXT_1)
        self._status_text.pack(side="left", padx=(0, 10), pady=4)

        self.badge_update = ctk.CTkButton(
            toolbar, text="↑ Update",
            font=(T.FONT, 11, "bold"), width=80, height=26, corner_radius=20,
            fg_color=T.CRIMSON, hover_color=T.CRIMSON_H, text_color=T.TEXT_0, cursor="hand2",
        )

        btn_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        btn_frame.grid(row=0, column=2, sticky="e", padx=16)

        self.btn_start = primary_btn(btn_frame, "▶  Start Camera", self._on_start_clicked, width=150)
        self.btn_start.pack(side="left", padx=(0, 8))
        self.btn_mirror = secondary_btn(btn_frame, "⬜  Mirror", self._on_mirror_clicked, width=100)
        self.btn_mirror.pack(side="left", padx=(0, 8))
        self.btn_stop = ctk.CTkButton(
            btn_frame, text="■  Stop",
            font=(T.FONT, 13, "bold"), width=90, height=36, corner_radius=T.R_SM,
            fg_color=T.BG_2, hover_color=T.RED, text_color=T.TEXT_1,
            state="disabled", command=self._on_stop_clicked,
        )
        self.btn_stop.pack(side="left")

    # ═══════════════════════════════════════════════════════════
    #  STATUS BAR
    # ═══════════════════════════════════════════════════════════
    def _build_statusbar(self):
        sb = ctk.CTkFrame(self, fg_color=T.BG_1, height=26, corner_radius=0)
        sb.grid(row=1, column=0, columnspan=2, sticky="ew")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(1, weight=1)
        from config.version import current_version
        make_label(sb, f"  {self.APP_NAME}  v{current_version}", size=10, color=T.TEXT_2).grid(
            row=0, column=0, sticky="w", padx=6
        )
        self._sb_label = make_label(sb, "📷 —   🖥 —", size=10, color=T.TEXT_2)
        self._sb_label.grid(row=0, column=1, sticky="e", padx=10)

    # ═══════════════════════════════════════════════════════════
    #  NAV SWITCHING
    # ═══════════════════════════════════════════════════════════
    def _switch_nav(self, key: str):
        self._active_nav = key
        titles = {
            "camera":  "Camera",
            "mirror":  "Screen Mirror",
            "devices": "Devices",
            "console": "Console & Logs",
        }
        self._set_nav_active(key)
        self._toolbar_title.configure(text=titles.get(key, key.title()))
        for k, page in self._pages.items():
            if k == key:
                page.tkraise()

    # ═══════════════════════════════════════════════════════════
    #  PAGE: CAMERA
    # ═══════════════════════════════════════════════════════════
    def _build_camera_page(self, parent):
        # row 0 = scrollable content (expands to fill)
        parent.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(
            parent, fg_color="transparent",
            scrollbar_button_color=T.BG_2, scrollbar_button_hover_color=T.BG_3,
        )
        scroll.grid(row=0, column=0, sticky="nsew", pady=(12, 0))
        scroll.grid_columnconfigure(0, weight=1)

        # Device
        _section_header(scroll, "Device", row=0)
        dev_card = make_card(scroll)
        dev_card.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        dev_card.grid_columnconfigure(0, weight=1)
        self._cam_device_sel = DeviceSelector(
            dev_card, "Camera Device",
            on_change=lambda ser: self._on_setting_change("camera_device", ser),
        )
        self._cam_device_sel.grid(row=0, column=0, sticky="ew", padx=16, pady=14)

        # Source
        _section_header(scroll, "Source", row=2)
        src_card = make_card(scroll)
        src_card.grid(row=3, column=0, sticky="ew", pady=(4, 12))
        src_card.grid_columnconfigure((0, 1), weight=1)

        self.var_cam = ctk.StringVar()
        self.opt_cam = themed_optmenu(src_card, ["Auto"], variable=self.var_cam, command=self._on_camera_change)
        _card_field(src_card, "Camera", self.opt_cam, row=0, col=0)

        self.opt_res = themed_optmenu(src_card, ["Auto", "720", "1080", "1920"],
                                      command=lambda v: self._on_setting_change("resolution", v))
        _card_field(src_card, "Resolution", self.opt_res, row=0, col=1)

        self.opt_fps = themed_optmenu(src_card, ["15", "24", "30"],
                                      command=lambda v: self._on_setting_change("fps", int(v)))
        _card_field(src_card, "FPS", self.opt_fps, row=2, col=0)

        self.opt_bit = themed_optmenu(src_card, ["4M", "8M", "16M", "24M"],
                                      command=lambda v: self._on_setting_change("bitrate", v))
        _card_field(src_card, "Bitrate", self.opt_bit, row=2, col=1)

        # Transform
        _section_header(scroll, "Transform", row=4)
        tr_card = make_card(scroll)
        tr_card.grid(row=5, column=0, sticky="ew", pady=(4, 12))
        tr_card.grid_columnconfigure((0, 1), weight=1)

        self.var_ar = ctk.StringVar(value="Auto")
        _card_field(tr_card, "Aspect Ratio",
                    themed_segmented(tr_card, ["16:9", "4:3", "Auto"], self.var_ar,
                                     command=lambda v: self._on_setting_change("aspect_ratio", v)),
                    row=0, col=0)

        btn_group = ctk.CTkFrame(tr_card, fg_color="transparent")
        btn_group.grid_columnconfigure((0, 1), weight=0)

        self.btn_mirror = ctk.CTkButton(
            btn_group,
            text="🪞 Mirror",
            command=self._on_camera_mirror_toggle,
            width=120,
            height=36,
            font=(T.FONT, 12, "bold"),
            corner_radius=T.R_SM,
            fg_color=T.BG_2,
            hover_color=T.BG_3,
            text_color=T.TEXT_0,
        )
        self.btn_mirror.grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.btn_rotate = ctk.CTkButton(
            btn_group,
            text="↻ 90°",
            command=self._on_camera_rotate_click,
            width=90,
            height=36,
            font=(T.FONT, 14, "bold"),
            corner_radius=T.R_SM,
            fg_color=T.BG_2,
            hover_color=T.BG_3,
            text_color=T.TEXT_0,
        )
        self.btn_rotate.grid(row=0, column=1, sticky="e")

        _card_field(tr_card, "Mirror & Rotate", btn_group, row=0, col=1)

        # Output
        _section_header(scroll, "Output", row=6)
        out_card = make_card(scroll)
        out_card.grid(row=7, column=0, sticky="ew", pady=(4, 12))
        out_card.grid_columnconfigure((0, 1), weight=1)

        self.opt_preview = themed_optmenu(out_card,
                                          ["Normal Window", "Borderless", "Always On Top", "Hidden Preview"],
                                          command=lambda v: self._on_setting_change("preview_mode", v))
        _card_field(out_card, "Preview Mode", self.opt_preview, row=0, col=0)

        self.opt_audio = themed_optmenu(out_card, ["Playback", "Mic", "Both", "Off"],
                                        command=lambda v: self._on_setting_change("audio_source", v))
        _card_field(out_card, "Audio Source", self.opt_audio, row=0, col=1)

    # ═══════════════════════════════════════════════════════════
    #  PAGE: MIRROR  (full layout fix)
    # ═══════════════════════════════════════════════════════════
    def _build_mirror_page(self, parent):
        # row 0 = scrollable content (expands to fill)
        parent.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(
            parent, fg_color="transparent",
            scrollbar_button_color=T.BG_2, scrollbar_button_hover_color=T.BG_3,
        )
        scroll.grid(row=0, column=0, sticky="nsew", pady=(12, 0))
        scroll.grid_columnconfigure(0, weight=1)

        # Device
        _section_header(scroll, "Device", row=0)
        dev_card = make_card(scroll)
        dev_card.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        dev_card.grid_columnconfigure(0, weight=1)

        self._mir_device_sel = DeviceSelector(
            dev_card, "Mirror Device",
            on_change=lambda ser: self._on_setting_change("mirror_device", ser),
        )
        self._mir_device_sel.grid(row=0, column=0, sticky="ew", padx=16, pady=12)

        note_row = ctk.CTkFrame(dev_card, fg_color=T.BG_2, corner_radius=T.R_SM)
        note_row.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))
        make_label(
            note_row,
            "ℹ  Mirror device is independent from Camera device.",
            size=10, color=T.TEXT_2
        ).pack(anchor="w", padx=10, pady=6)

        # Settings
        _section_header(scroll, "Settings", row=2)
        cfg_card = make_card(scroll)
        cfg_card.grid(row=3, column=0, sticky="ew", pady=(4, 12))
        cfg_card.grid_columnconfigure((0, 1), weight=1)

        self.opt_mirror_res = themed_optmenu(
            cfg_card, ["Auto", "720", "1080", "1920", "Native"],
            command=lambda v: self._on_setting_change("mirror_resolution", v)
        )
        _card_field(cfg_card, "Resolution", self.opt_mirror_res, row=0, col=0)

        self.opt_mirror_bit = themed_optmenu(
            cfg_card, ["Auto", "4M", "8M", "16M", "24M"],
            command=lambda v: self._on_setting_change("mirror_bitrate", v)
        )
        _card_field(cfg_card, "Bitrate", self.opt_mirror_bit, row=0, col=1)

        _build_screenshot_row(cfg_card, row=2, on_change=lambda v: self._on_setting_change("screenshot_path", v))
        self.var_screenshot_path = cfg_card._ss_var
        self.ent_screenshot_path = cfg_card._ss_entry
        self.btn_browse_path     = cfg_card._ss_browse

        # Launch
        _section_header(scroll, "Control", row=4)
        launch_card = make_card(scroll)
        launch_card.grid(row=5, column=0, sticky="ew", pady=(4, 12))
        launch_card.grid_columnconfigure(0, weight=1)

        btn_row = ctk.CTkFrame(launch_card, fg_color="transparent")
        btn_row.grid(row=0, column=0, sticky="ew", padx=16, pady=16)
        btn_row.grid_columnconfigure(1, weight=1)

        self.btn_start_mirror = primary_btn(
            btn_row, "▶  Launch Mirror", self._on_mirror_clicked, width=160
        )
        self.btn_start_mirror.grid(row=0, column=0)

        make_label(
            btn_row,
            "A floating control bar will appear next to\nthe mirror window.",
            size=10, color=T.TEXT_2
        ).grid(row=0, column=1, sticky="w", padx=(16, 0))

        # Keyboard shortcuts
        _section_header(scroll, "Keyboard Shortcuts", row=6)
        tips_card = make_card(scroll)
        tips_card.grid(row=7, column=0, sticky="ew", pady=(4, 16))

        shortcuts = [
            ("Ctrl+H", "Go Home"),
            ("Ctrl+B", "Go Back"),
            ("Ctrl+P", "Toggle screen power"),
            ("Ctrl+↑", "Volume up"),
            ("Ctrl+↓", "Volume down"),
            ("Ctrl+R", "Rotate device"),
            ("Ctrl+S", "Take screenshot"),
        ]
        for i, (key, desc) in enumerate(shortcuts):
            rw = ctk.CTkFrame(tips_card, fg_color="transparent")
            rw.grid(row=i, column=0, sticky="ew", padx=16, pady=3)
            rw.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                rw, text=key, font=(T.MONO, 11, "bold"),
                fg_color=T.BG_2, corner_radius=4, text_color=T.AMBER,
                width=90, height=24,
            ).grid(row=0, column=0, padx=(0, 12))
            make_label(rw, desc, size=11, color=T.TEXT_1).grid(row=0, column=1, sticky="w")
        ctk.CTkFrame(tips_card, fg_color="transparent", height=8).grid(row=len(shortcuts), column=0)

    # ═══════════════════════════════════════════════════════════
    #  PAGE: DEVICES
    # ═══════════════════════════════════════════════════════════
    def _build_devices_page(self, parent):
        # row 0 = header, row 1 = scrollable content
        parent.grid_rowconfigure(0, weight=0)
        parent.grid_rowconfigure(1, weight=1)

        # ── Header ──────────────────────────────────────────────
        hdr = ctk.CTkFrame(parent, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(12, 6))
        hdr.grid_columnconfigure(1, weight=1)
        make_label(hdr, "Connected Devices", size=14, weight="bold", color=T.TEXT_0).grid(
            row=0, column=0, sticky="w"
        )
        ghost_btn(hdr, "⟳  Refresh", self._on_refresh_devices, width=100).grid(
            row=0, column=2, sticky="e"
        )
        ghost_btn(hdr, "Test ADB", self._on_test_adb_clicked, width=90).grid(
            row=0, column=3, sticky="e", padx=(8, 0)
        )
        ghost_btn(hdr, "Restart ADB", self._on_restart_adb_clicked, width=100).grid(
            row=0, column=4, sticky="e", padx=(8, 0)
        )

        # ── Scrollable body ──────────────────────────────────────
        self._dev_page_scroll = ctk.CTkScrollableFrame(
            parent, fg_color="transparent",
            scrollbar_button_color=T.BG_2, scrollbar_button_hover_color=T.BG_3,
        )
        self._dev_page_scroll.grid(row=1, column=0, sticky="nsew")
        self._dev_page_scroll.grid_columnconfigure(0, weight=1)

        # No-device banner
        self.lbl_no_device = make_label(
            self._dev_page_scroll,
            "No device detected.\nConnect a device via USB, then click Enable Wireless.",
            size=12, color=T.TEXT_2,
        )
        self.lbl_no_device.grid(row=0, column=0, sticky="ew", padx=20, pady=24)
        self.device_rows = []

        # ── Manual Wireless Connection (collapsible) ─────────────
        self._build_manual_connect_section(self._dev_page_scroll, row=200)

        # ── Advanced Logs (collapsible) ──────────────────────────
        self._build_advanced_logs_section(self._dev_page_scroll, row=300)

        # keep legacy reference for old code that uses list_container
        self.list_container = self._dev_page_scroll

    def _build_manual_connect_section(self, parent, row):
        """Expandable manual wireless connection form."""
        # Toggle header
        self._manual_sec_expanded = False
        toggle_frame = ctk.CTkFrame(parent, fg_color="transparent")
        toggle_frame.grid(row=row, column=0, sticky="ew", pady=(8, 0))
        toggle_frame.grid_columnconfigure(1, weight=1)

        self._btn_manual_toggle = ctk.CTkButton(
            toggle_frame,
            text="▶  Manual Wireless Connection",
            anchor="w",
            font=(T.FONT, 11, "bold"),
            height=30, fg_color="transparent",
            hover_color=T.BG_2, text_color=T.TEXT_2,
            corner_radius=T.R_SM,
            command=self._toggle_manual_connect,
        )
        self._btn_manual_toggle.grid(row=0, column=0, columnspan=2, sticky="ew")

        # Content (hidden by default)
        self._manual_sec_frame = make_card(parent)
        # NOT gridded yet — shown on toggle
        self._manual_sec_row = row + 1
        self._manual_sec_parent = parent

        inner = ctk.CTkFrame(self._manual_sec_frame, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=14)
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_columnconfigure(1, weight=0)

        make_label(inner, "IP Address", size=11, color=T.TEXT_2).grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self._manual_ip_var = ctk.StringVar()
        ctk.CTkEntry(
            inner, textvariable=self._manual_ip_var,
            placeholder_text="192.168.1.x",
            placeholder_text_color=T.TEXT_2,
            font=(T.MONO, 12), fg_color=T.BG_2, text_color=T.TEXT_0,
            border_color=T.BORDER, border_width=1, corner_radius=T.R_SM, height=34,
        ).grid(row=1, column=0, sticky="ew")

        make_label(inner, "Port", size=11, color=T.TEXT_2).grid(
            row=0, column=1, sticky="w", padx=(12, 0), pady=(0, 4)
        )
        self._manual_port_var = ctk.StringVar(value="5555")
        ctk.CTkEntry(
            inner, textvariable=self._manual_port_var, width=80,
            font=(T.MONO, 12), fg_color=T.BG_2, text_color=T.TEXT_0,
            border_color=T.BORDER, border_width=1, corner_radius=T.R_SM, height=34,
        ).grid(row=1, column=1, padx=(12, 0))

        self._manual_status_lbl = make_label(inner, "", size=11, color=T.TEXT_2)
        self._manual_status_lbl.grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self._btn_manual_connect = primary_btn(
            inner, "Connect", self._on_manual_connect_clicked, width=110
        )
        self._btn_manual_connect.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _toggle_manual_connect(self):
        self._manual_sec_expanded = not self._manual_sec_expanded
        if self._manual_sec_expanded:
            self._btn_manual_toggle.configure(text="▼  Manual Wireless Connection")
            self._manual_sec_frame.grid(
                in_=self._manual_sec_parent,
                row=self._manual_sec_row, column=0, sticky="ew", pady=(0, 8)
            )
        else:
            self._btn_manual_toggle.configure(text="▶  Manual Wireless Connection")
            self._manual_sec_frame.grid_remove()

    def _on_manual_connect_clicked(self):
        ip = self._manual_ip_var.get().strip()
        port_str = self._manual_port_var.get().strip()
        if not ip:
            self._manual_status_lbl.configure(text="❌ Enter an IP address.", text_color=T.RED)
            return
        try:
            port = int(port_str)
        except ValueError:
            self._manual_status_lbl.configure(text="❌ Invalid port number.", text_color=T.RED)
            return
        self._manual_status_lbl.configure(text="Connecting…", text_color=T.TEXT_2)
        self._btn_manual_connect.configure(state="disabled")

        def worker():
            adb = getattr(self, "_adb_manager", None)
            if not adb:
                self.after(0, lambda: self._manual_status_lbl.configure(
                    text="❌ ADB not available.", text_color=T.RED
                ))
                self.after(0, lambda: self._btn_manual_connect.configure(state="normal"))
                return
            adb.connect_wireless(ip, port, on_done=self._on_manual_connect_done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_manual_connect_done(self, success: bool, message: str):
        def update():
            self._btn_manual_connect.configure(state="normal")
            if success:
                self._manual_status_lbl.configure(text=f"✓ {message}", text_color=T.GREEN)
                self.append_log(f"Manual WiFi connect: {message}")
            else:
                self._manual_status_lbl.configure(text=f"❌ {message}", text_color=T.RED)
                self.append_log(f"Manual WiFi connect failed: {message}")
        self.after(0, update)

    def _build_advanced_logs_section(self, parent, row):
        """Collapsible advanced logs section in devices page."""
        self._adv_logs_expanded = False
        toggle_frame = ctk.CTkFrame(parent, fg_color="transparent")
        toggle_frame.grid(row=row, column=0, sticky="ew", pady=(8, 0))

        ctk.CTkButton(
            toggle_frame,
            text="▶  Advanced Logs",
            anchor="w",
            font=(T.FONT, 11, "bold"),
            height=30, fg_color="transparent",
            hover_color=T.BG_2, text_color=T.TEXT_2,
            corner_radius=T.R_SM,
            command=lambda: self._switch_nav("console"),
        ).pack(fill="x")

    # ═══════════════════════════════════════════════════════════
    #  PAGE: CONSOLE
    # ═══════════════════════════════════════════════════════════
    def _build_console_page(self, parent):
        # row 0 = header bar, row 1 = textbox (expands to fill available space)
        parent.grid_rowconfigure(0, weight=0)
        parent.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(parent, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(12, 6))
        make_label(hdr, "Console Output", size=14, weight="bold", color=T.TEXT_0).pack(side="left")
        ghost_btn(hdr, "Clear", self._clear_log, width=70).pack(side="right")
        ghost_btn(hdr, "📋  Logs", self._switch_nav_console, width=90).pack(side="right", padx=(0, 8))

        self.txt_log = ctk.CTkTextbox(
            parent,
            state="disabled",
            wrap="word",
            fg_color=T.BG_1,
            text_color=T.TEXT_0,
            font=(T.MONO, 12),
            corner_radius=T.R_MD,
            border_width=1,
            border_color=T.BORDER,
            scrollbar_button_color=T.BG_2,
            scrollbar_button_hover_color=T.BG_3,
        )
        self.txt_log.grid(row=1, column=0, sticky="nsew", pady=(0, 12))
        try:
            self.txt_log.tag_config("normal", foreground=T.TEXT_0)
            self.txt_log.tag_config("error",  foreground=T.RED)
        except Exception:
            pass

    def _switch_nav_console(self):
        self._switch_nav("console")

    def _clear_log(self):
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")

    # ═══════════════════════════════════════════════════════════
    #  DEVICE LIST UPDATE
    # ═══════════════════════════════════════════════════════════
    def update_device_list(self, devices):
        self._all_devices = devices

        cam_serial = getattr(self, "current_settings", {}).get("camera_device", "")
        mir_serial = getattr(self, "current_settings", {}).get("mirror_device", "")
        if hasattr(self, "_cam_device_sel"):
            self._cam_device_sel.update_devices(devices, cam_serial)
        if hasattr(self, "_mir_device_sel"):
            self._mir_device_sel.update_devices(devices, mir_serial)

        for row in self.device_rows:
            row.destroy()
        self.device_rows.clear()

        container = getattr(self, "_dev_page_scroll", getattr(self, "list_container", None))
        if not container:
            return

        if not devices:
            self.lbl_no_device.grid(row=0, column=0, sticky="ew", padx=20, pady=24)
            self._on_setting_change("target_device", "")
            self._sb_label.configure(text="📷 —   🖥 —")
            return

        self.lbl_no_device.grid_forget()
        for index, dev in enumerate(devices):
            card = self._build_device_card(container, dev, index)
            self.device_rows.append(card)

        self._update_statusbar_devices()

    def _build_device_card(self, parent, dev, index):
        """Build a rich device card with action buttons."""
        serial = dev.serial
        model  = dev.model_name
        status = dev.status
        conn   = dev.connection_type
        ip     = dev.ip_address

        # Status text/color
        if status == "device":
            status_label = "Connected"
            status_color = T.GREEN
        elif status == "unauthorized":
            status_label = "Unauthorized — allow on device"
            status_color = T.RED
        else:
            status_label = status.capitalize()
            status_color = T.YELLOW

        conn_icon  = dev.conn_icon
        conn_color = T.YELLOW if conn == "WiFi" else T.GREEN
        conn_text  = (f"{conn_icon}  WiFi  ·  {ip}:{serial.split(':')[1] if ':' in serial else '5555'}"
                      if conn == "WiFi" else f"{conn_icon}  USB")

        # ── Card shell ───────────────────────────────────────────
        card = make_card(parent)
        card.grid(row=index, column=0, sticky="ew", pady=(0, 10), padx=4)
        card.grid_columnconfigure(1, weight=1)

        # Left icon pill
        icon_pill = ctk.CTkFrame(card, fg_color=T.BG_2, corner_radius=T.R_SM, width=56)
        icon_pill.grid(row=0, column=0, rowspan=3, sticky="ns", padx=(14, 0), pady=14)
        icon_pill.grid_propagate(False)
        make_label(icon_pill, conn_icon, size=20, color=conn_color).pack(expand=True)

        # Model / serial
        info = ctk.CTkFrame(card, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", padx=14, pady=(14, 2))
        make_label(info, model, size=13, weight="bold", color=T.TEXT_0).pack(anchor="w")
        make_label(info, serial, size=10, color=T.TEXT_2).pack(anchor="w", pady=(1, 0))

        # Connection + status badges
        badges = ctk.CTkFrame(card, fg_color="transparent")
        badges.grid(row=1, column=1, sticky="ew", padx=14, pady=(0, 6))
        ctk.CTkLabel(
            badges, text=conn_text,
            font=(T.FONT, 10, "bold"),
            fg_color=T.BG_2, corner_radius=4, text_color=conn_color, padx=8, pady=2
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            badges, text=status_label,
            font=(T.FONT, 10),
            fg_color=T.BG_2, corner_radius=4, text_color=status_color, padx=8, pady=2
        ).pack(side="left")

        # Inline error / success message label (hidden by default)
        card._msg_lbl = make_label(card, "", size=11, color=T.TEXT_2)
        card._msg_lbl.grid(row=2, column=1, sticky="ew", padx=14, pady=(0, 4))
        card._msg_lbl.grid_remove()

        # ── Action buttons ───────────────────────────────────────
        if status == "device":
            act = ctk.CTkFrame(card, fg_color="transparent")
            act.grid(row=0, column=2, rowspan=3, sticky="ns", padx=(6, 14), pady=14)

            if conn == "USB":
                # Enable Wireless button
                btn_wifi = ctk.CTkButton(
                    act, text="Enable Wireless",
                    font=(T.FONT, 11, "bold"), width=136, height=32,
                    corner_radius=T.R_SM, fg_color=T.ORANGE, hover_color=T.ORANGE_H,
                    text_color=T.TEXT_0,
                    command=lambda s=serial, c=card: self._start_enable_wifi(s, c),
                )
                btn_wifi.pack(pady=(0, 6))

                ghost_btn(
                    act, "Open Shell",
                    command=lambda s=serial: self._open_shell(s),
                    width=136, height=28
                ).pack(pady=(0, 2))

            else:  # WiFi device
                ctk.CTkButton(
                    act, text="Reconnect",
                    font=(T.FONT, 11, "bold"), width=136, height=32,
                    corner_radius=T.R_SM, fg_color=T.BG_2, hover_color=T.AMBER,
                    text_color=T.TEXT_1,
                    command=lambda s=serial, c=card: self._reconnect_wifi_device(s, c),
                ).pack(pady=(0, 6))

                ctk.CTkButton(
                    act, text="Disconnect",
                    font=(T.FONT, 11, "bold"), width=136, height=32,
                    corner_radius=T.R_SM, fg_color=T.BG_2, hover_color=T.RED,
                    text_color=T.TEXT_1,
                    command=lambda s=serial, c=card: self._disconnect_wifi_device(s, c),
                ).pack()

        return card

    # ── Device card action helpers ────────────────────────────────

    def _show_card_msg(self, card, text: str, color=None):
        """Show an inline message on a device card."""
        msg_lbl = getattr(card, "_msg_lbl", None)
        if not widget_is_alive(msg_lbl):
            return
        color = color or T.TEXT_2
        try:
            msg_lbl.configure(text=text, text_color=color)
            msg_lbl.grid()
        except Exception:
            pass

    def _start_enable_wifi(self, serial: str, card):
        """Phase 1: tcpip + IP detection → show IP selection / confirmation dialog."""
        self._show_card_msg(card, "Enabling wireless…  Please wait.", T.TEXT_2)
        self.append_log(f"Starting WiFi ADB for {serial}…")

        def worker():
            adb = getattr(self, "_adb_manager", None)
            if not adb:
                self.after(0, lambda: self._show_card_msg(card, "❌ ADB not available.", T.RED))
                return
            adb.enable_wifi_adb_with_ip_callback(
                serial,
                on_ip_found=lambda ip_list, err: self.after(
                    0, lambda: self._on_ip_detected(serial, ip_list, err, card)
                )
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_ip_detected(self, serial: str, ip_list: list, error: str, card):
        """Phase 1 done: handle ip_list (list of dicts) or error."""
        if error or not ip_list:
            msg = error or "Could not detect device IP address."
            self._show_card_msg(card, f"❌ {msg}", T.RED)
            self.append_log(f"WiFi ADB failed: {msg}")
            return

        detected_labels = [f"{e['ip']}  —  {e['label']}" for e in ip_list]
        self.append_log(
            f"Detected {len(ip_list)} address(es): " +
            ", ".join(e['ip'] for e in ip_list)
        )

        # Clear loading message safely if the card is still alive.
        msg_lbl = getattr(card, "_msg_lbl", None)
        if widget_is_alive(msg_lbl):
            try:
                msg_lbl.grid_remove()
            except Exception:
                pass

        if len(ip_list) == 1:
            # Only one address — go straight to confirm dialog
            self._show_wifi_confirm_dialog(serial, ip_list[0]["ip"], ip_list, card)
        else:
            # Multiple addresses — show IP selection dialog first
            self._show_ip_selection_dialog(serial, ip_list, card)

    def _show_ip_selection_dialog(self, serial: str, ip_list: list, card):
        """Radio-button dialog to choose which detected IP to connect with."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Select Network Address")
        h = min(200 + len(ip_list) * 54, 480)
        dlg.geometry(f"460x{h}")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        dlg.focus_set()
        dlg.configure(fg_color=T.BG_0)
        self._set_window_icon(dlg)
        px = self.winfo_x() + (self.winfo_width()  - 460) // 2
        py = self.winfo_y() + (self.winfo_height() - h)   // 2
        dlg.geometry(f"460x{h}+{px}+{py}")

        c = ctk.CTkFrame(dlg, fg_color="transparent")
        c.pack(fill="both", expand=True, padx=24, pady=20)

        make_label(c, "📡  Select Network Address", size=14, weight="bold", color=T.TEXT_0).pack(
            anchor="w", pady=(0, 4)
        )
        make_label(
            c,
            f"Multiple addresses detected for {serial}.\n"
            "Select the WiFi address your PC can reach.",
            size=11, color=T.TEXT_2
        ).pack(anchor="w", pady=(0, 14))

        # Radio buttons for each IP
        sel_var = ctk.StringVar(value=ip_list[0]["ip"])  # pre-select best (sorted WiFi first)

        radio_frame = ctk.CTkScrollableFrame(
            c, fg_color="transparent", height=min(len(ip_list) * 54, 240),
            scrollbar_button_color=T.BG_2,
        )
        radio_frame.pack(fill="x", pady=(0, 14))

        for entry in ip_list:
            ip    = entry["ip"]
            label = entry["label"]
            # Color: WiFi = green, others = amber
            is_wifi = "WiFi" in label
            dot_color = T.GREEN if is_wifi else T.AMBER

            row = make_card(radio_frame)
            row.pack(fill="x", pady=(0, 6))
            row.grid_columnconfigure(1, weight=1)

            ctk.CTkRadioButton(
                row,
                text="",
                variable=sel_var,
                value=ip,
                width=20,
                fg_color=T.AMBER,
                hover_color=T.AMBER_H,
                border_color=T.BORDER_L,
            ).grid(row=0, column=0, padx=(12, 6), pady=12)

            ip_lbl_frame = ctk.CTkFrame(row, fg_color="transparent")
            ip_lbl_frame.grid(row=0, column=1, sticky="ew", pady=10)
            make_label(ip_lbl_frame, ip, size=13, weight="bold", color=T.TEXT_0).pack(anchor="w")
            make_label(ip_lbl_frame, label, size=10, color=dot_color).pack(anchor="w", pady=(1, 0))

        bf = ctk.CTkFrame(c, fg_color="transparent")
        bf.pack(fill="x", side="bottom")

        def on_select():
            chosen = sel_var.get()
            dlg.destroy()
            self._show_wifi_confirm_dialog(serial, chosen, ip_list, card)

        primary_btn(bf, "Continue", on_select, width=120).pack(side="right")
        ghost_btn(bf, "Cancel", dlg.destroy, width=80).pack(side="right", padx=(0, 8))


    def _show_wifi_confirm_dialog(self, serial: str, detected_ip: str, ip_list: list, card):
        """Confirmation dialog: auto-filled IP + port, with Connect button."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Enable Wireless ADB")
        dlg.geometry("420x340")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.grab_set()
        dlg.focus_set()
        dlg.configure(fg_color=T.BG_0)
        self._set_window_icon(dlg)
        # Center on main window
        px = self.winfo_x() + (self.winfo_width()  - 420) // 2
        py = self.winfo_y() + (self.winfo_height() - 340) // 2
        dlg.geometry(f"420x340+{px}+{py}")

        c = ctk.CTkFrame(dlg, fg_color="transparent")
        c.pack(fill="both", expand=True, padx=24, pady=20)
        c.grid_columnconfigure(0, weight=1)
        c.grid_columnconfigure(1, weight=0)

        make_label(c, "📶  Wireless ADB", size=14, weight="bold", color=T.TEXT_0).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        make_label(c, f"Device:  {serial}", size=10, color=T.TEXT_2).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 14)
        )

        make_label(c, "Device IP", size=11, color=T.TEXT_2).grid(row=2, column=0, sticky="w", pady=(0, 4))
        make_label(c, "Port", size=11, color=T.TEXT_2).grid(row=2, column=1, sticky="w", padx=(12, 0), pady=(0, 4))

        dlg_ip_var   = ctk.StringVar(value=detected_ip)
        dlg_port_var = ctk.StringVar(value="5555")
        ctk.CTkEntry(
            c, textvariable=dlg_ip_var,
            font=(T.MONO, 13), fg_color=T.BG_2, text_color=T.TEXT_0,
            border_color=T.BORDER, border_width=1, corner_radius=T.R_SM, height=36,
        ).grid(row=3, column=0, sticky="ew")
        ctk.CTkEntry(
            c, textvariable=dlg_port_var, width=80,
            font=(T.MONO, 13), fg_color=T.BG_2, text_color=T.TEXT_0,
            border_color=T.BORDER, border_width=1, corner_radius=T.R_SM, height=36,
        ).grid(row=3, column=1, padx=(12, 0))

        status_lbl = make_label(c, "", size=11, color=T.TEXT_2, wraplength=370, justify="left")
        status_lbl.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        bf = ctk.CTkFrame(c, fg_color="transparent")
        bf.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(14, 0))

        btn_connect = primary_btn(bf, "Connect", lambda: None, width=110)
        btn_connect.pack(side="right")
        ghost_btn(bf, "Cancel", dlg.destroy, width=80).pack(side="right", padx=(0, 8))

        def do_connect():
            ip   = dlg_ip_var.get().strip()
            port_s = dlg_port_var.get().strip()
            if not ip:
                status_lbl.configure(text="❌ Enter an IP address.", text_color=T.RED)
                return
            try:
                port = int(port_s)
            except ValueError:
                status_lbl.configure(text="❌ Invalid port number.", text_color=T.RED)
                return

            btn_connect.configure(state="disabled", text="Connecting…")
            status_lbl.configure(text="Connecting to device…", text_color=T.TEXT_2)

            def worker():
                adb = getattr(self, "_adb_manager", None)
                if not adb:
                    dlg.after(0, lambda: status_lbl.configure(
                        text="❌ ADB manager not available.", text_color=T.RED
                    ))
                    dlg.after(0, lambda: btn_connect.configure(state="normal", text="Connect"))
                    return
                adb.connect_wireless(
                    ip, port,
                    on_done=lambda ok, msg: dlg.after(0, lambda: on_connect_result(ok, msg, dlg))
                )

            def on_connect_result(ok: bool, msg: str, dialog):
                """Handle adb connect result — always runs on main thread via dlg.after()."""
                import traceback
                try:
                    # Guard: dialog may have been destroyed during the async wait
                    if not dialog.winfo_exists():
                        return
                    if ok:
                        try:
                            status_lbl.configure(text=f"✓ {msg}", text_color=T.GREEN)
                        except Exception:
                            pass
                        self.append_log(f"WiFi ADB: {msg}")
                        # Refresh device list so the new WiFi device appears immediately
                        self._trigger_device_refresh()
                        try:
                            dialog.after(1500, lambda: _safe_destroy(dialog))
                        except Exception:
                            pass
                    else:
                        try:
                            current_ip = dlg_ip_var.get().strip()
                        except Exception:
                            current_ip = "unknown"
                        fail_text = (
                            f"❌ Cannot connect to detected WiFi address\n"
                            f"Detected: {current_ip}\n"
                            f"Please verify the IP or enter it manually."
                        )
                        try:
                            status_lbl.configure(text=fail_text, text_color=T.RED)
                            btn_connect.configure(state="normal", text="Retry")
                        except Exception:
                            pass
                        self.append_log(f"WiFi ADB failed: {msg}  (tried {current_ip})")
                except Exception:
                    tb = traceback.format_exc()
                    print("[CameraStudio] on_connect_result error:\n" + tb)
                    self.append_log(f"[ERROR] WiFi callback error: {tb.strip().splitlines()[-1]}")

            def _safe_destroy(dialog):
                try:
                    if dialog.winfo_exists():
                        dialog.destroy()
                except Exception:
                    pass

            btn_connect.configure(command=do_connect)   # rebind for retry
            threading.Thread(target=worker, daemon=True).start()

        btn_connect.configure(command=do_connect)

    def _reconnect_wifi_device(self, serial: str, card):
        self._show_card_msg(card, "Reconnecting…", T.TEXT_2)
        self.append_log(f"Reconnecting {serial}…")

        def worker():
            adb = getattr(self, "_adb_manager", None)
            if not adb:
                self.after(0, lambda: self._show_card_msg(card, "❌ ADB not available.", T.RED))
                return
            adb.reconnect_wifi(
                serial,
                on_done=lambda ok, msg: self.after(0, lambda: self._on_reconnect_done(ok, msg, card))
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_reconnect_done(self, ok: bool, msg: str, card):
        if ok:
            self._show_card_msg(card, f"✓ {msg}", T.GREEN)
        else:
            self._show_card_msg(card, f"❌ {msg}", T.RED)
        self.append_log(f"Reconnect: {'OK' if ok else 'Failed'}  {msg}")

    def _disconnect_wifi_device(self, serial: str, card):
        self._show_card_msg(card, "Disconnecting…", T.TEXT_2)
        self.append_log(f"Disconnecting {serial}…")

        def worker():
            adb = getattr(self, "_adb_manager", None)
            if not adb:
                self.after(0, lambda: self._show_card_msg(card, "❌ ADB not available.", T.RED))
                return
            adb.disconnect_wifi(
                serial,
                on_done=lambda ok, msg: self.after(0, lambda: self._on_disconnect_done(ok, msg, card))
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_disconnect_done(self, ok: bool, msg: str, card):
        if ok:
            self._show_card_msg(card, f"✓ Disconnected.", T.TEXT_2)
        else:
            self._show_card_msg(card, f"❌ {msg}", T.RED)
        self.append_log(f"Disconnect: {'OK' if ok else 'Failed'}  {msg}")

    def _open_shell(self, serial: str):
        """Open an ADB shell in a new terminal window."""
        from config.config import Config
        adb = Config.get_bin_path("adb")
        cmd = f"{adb} -s {serial} shell"
        try:
            import subprocess
            if os.name == "nt":
                subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", cmd])
            else:
                terminals = ["x-terminal-emulator", "gnome-terminal", "xterm", "konsole", "xfce4-terminal"]
                for term in terminals:
                    try:
                        if term == "gnome-terminal":
                            subprocess.Popen([term, "--", "bash", "-c", cmd + "; exec bash"])
                        else:
                            subprocess.Popen([term, "-e", cmd])
                        break
                    except FileNotFoundError:
                        continue
            self.append_log(f"Opened shell for device: {serial}")
        except Exception as e:
            self.append_log(f"Could not open terminal: {e}")

    # ── legacy wrappers kept for backward compat ─────────────────
    def _enable_wifi_adb(self, serial: str, card_widget):
        self._start_enable_wifi(serial, card_widget)

    def _on_wifi_enable_done(self, success: bool, message: str):
        icon = "✓" if success else "✗"
        self.after(0, lambda: self.append_log(f"{icon}  {message}"))

    def _disconnect_wifi(self, serial: str):
        self.append_log(f"Disconnecting: {serial}…")
        def worker():
            adb = getattr(self, "_adb_manager", None)
            if adb:
                adb.disconnect_wifi(
                    serial,
                    on_done=lambda ok, msg: self.after(0, lambda: self.append_log(f"{'✓' if ok else '✗'}  {msg}"))
                )
        threading.Thread(target=worker, daemon=True).start()

    def _update_statusbar_devices(self):
        cam_ser = getattr(self, "current_settings", {}).get("camera_device", "")
        mir_ser = getattr(self, "current_settings", {}).get("mirror_device", "")
        def model_for(s):
            for d in self._all_devices:
                if d.serial == s and d.status == "device":
                    return d.model_name
            return "—"
        self._sb_label.configure(
            text=f"📷 {model_for(cam_ser)}   🖥 {model_for(mir_ser)}"
        )

    def _on_refresh_devices(self):
        self.append_log("Refreshing device list…")
        self._trigger_device_refresh()

    def _on_test_adb_clicked(self):
        """Run adb start-server and adb devices to verify ADB is available."""
        self.append_log("Testing ADB connection…")

        def worker():
            adb = getattr(self, "_adb_manager", None)
            if not adb:
                self.after(0, lambda: self.append_log("[ERROR] ADB manager not available."))
                return

            def on_done(ok: bool, msg: str):
                self.after(0, lambda: self._handle_adb_test_result(ok, msg))

            adb.test_adb_connection(on_done=on_done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_restart_adb_clicked(self):
        """Restart the ADB server from the Devices page."""
        self.append_log("Restarting ADB server…")

        def worker():
            adb = getattr(self, "_adb_manager", None)
            if not adb:
                self.after(0, lambda: self.append_log("[ERROR] ADB manager not available."))
                return

            def on_done(ok: bool, msg: str):
                self.after(0, lambda: self._handle_adb_restart_result(ok, msg))

            adb.restart_adb(on_done=on_done)

        threading.Thread(target=worker, daemon=True).start()

    def _handle_adb_test_result(self, ok: bool, msg: str):
        if ok:
            self.append_log(f"ADB test OK: {msg}")
        else:
            self.append_log(f"ADB test failed: {msg}")

    def _handle_adb_restart_result(self, ok: bool, msg: str):
        if ok:
            self.append_log(f"ADB restart OK: {msg}")
        else:
            self.append_log(f"ADB restart failed: {msg}")

    def _trigger_device_refresh(self):
        """Immediately poll ADB and update device list. Safe to call from any thread."""
        def do_refresh():
            try:
                adb = getattr(self, "_adb_manager", None)
                if not adb:
                    return
                devices = adb.get_connected_devices()
                self.after(0, lambda d=devices: self.update_device_list(d))
            except Exception:
                import traceback
                tb = traceback.format_exc()
                print("[CameraStudio] _trigger_device_refresh error:\n" + tb)
                try:
                    self.after(0, lambda: self.append_log(
                        f"[ERROR] Device refresh failed: {tb.strip().splitlines()[-1]}"
                    ))
                except Exception:
                    pass
        threading.Thread(target=do_refresh, daemon=True).start()

    # ═══════════════════════════════════════════════════════════
    #  CAMERA OPTIONS
    # ═══════════════════════════════════════════════════════════
    def update_camera_options(self, cameras):
        self.camera_options = cameras
        options = ["Auto"] + [c["label"] for c in cameras]
        self.opt_cam.configure(values=options)
        current_id = self.var_cam.get().replace("Camera ", "").split(" ")[0].strip()
        selected = "Auto"
        for c in cameras:
            if c["id"] == current_id:
                selected = c["label"]
                break
        if selected == "Auto" and cameras:
            selected = cameras[0]["label"]
        self.opt_cam.set(selected)
        self._on_camera_change(selected)

    # ═══════════════════════════════════════════════════════════
    #  STATUS UPDATE
    # ═══════════════════════════════════════════════════════════
    def set_camera_state(self, is_running):
        if isinstance(is_running, bool):
            statuses = {"camera": is_running, "mirror": False}
        else:
            statuses = is_running
        cam = statuses.get("camera", False)
        mir = statuses.get("mirror", False)

        if cam and mir:   txt, col = "Camera & Mirror Active", T.GREEN
        elif cam:         txt, col = "Camera Active", T.GREEN
        elif mir:         txt, col = "Mirror Active", T.GREEN
        else:             txt, col = "Stopped", T.RED

        self._status_dot.configure(text_color=col)
        self._status_text.configure(text=txt, text_color=col)
        self.btn_start.configure(state="disabled" if cam else "normal")
        self.btn_mirror.configure(state="disabled" if mir else "normal")
        if hasattr(self, "btn_start_mirror"):
            self.btn_start_mirror.configure(state="disabled" if mir else "normal")
        self.btn_stop.configure(
            state="normal" if (cam or mir) else "disabled",
            fg_color=T.RED if (cam or mir) else T.BG_2,
            text_color=T.TEXT_0 if (cam or mir) else T.TEXT_1,
        )

        if cam != self._prev_statuses.get("camera", False):
            self.append_log("Camera stream started." if cam else "Camera stream stopped.")
        if mir != self._prev_statuses.get("mirror", False):
            self.append_log("Mirror stream started." if mir else "Mirror stream stopped.")
        self._prev_statuses   = {"camera": cam, "mirror": mir}
        self._scrcpy_running_ui = cam or mir

    def update_scrcpy_status(self, is_running):
        self.set_camera_state(is_running)

    # ── update badge ─────────────────────────────────────────
    def show_update_badge(self, show=True):
        if show:
            self.badge_update.grid(row=0, column=1, padx=8)
        else:
            try:
                self.badge_update.grid_forget()
            except Exception:
                pass

    def handle_update_result(self, result):
        self.update_result = result
        self.show_update_badge(result.get("is_update_available", False))

    # ── dependency status ─────────────────────────────────────
    def update_dependency_status(self, dep_name, is_found, is_optional=False):
        pair = self.status_labels.get(dep_name)
        if not pair:
            return
        dot, lbl = pair
        if is_found:
            dot.configure(text_color=T.GREEN); lbl.configure(text_color=T.GREEN)
            self.append_log(f"Dependency check: {dep_name.upper()} is ready.")
        elif is_optional:
            dot.configure(text_color=T.YELLOW); lbl.configure(text_color=T.TEXT_2)
            self.append_log(f"Dependency check: {dep_name.upper()} missing (optional).")
        else:
            dot.configure(text_color=T.RED); lbl.configure(text_color=T.RED)
            self.append_log(f"Error: Required dependency {dep_name.upper()} is missing.")

    def show_installer_flow(self, is_missing):
        if is_missing:
            self.btn_install.pack(fill="x", padx=8, pady=(0, 4))
            self.btn_start.configure(state="disabled")
            self.btn_mirror.configure(state="disabled")
            self.append_log("Action required: Missing dependencies detected.")
        else:
            self.btn_install.pack_forget()
            if not self._scrcpy_running_ui:
                self.btn_start.configure(state="normal")
                self.btn_mirror.configure(state="normal")

    # ── callbacks ─────────────────────────────────────────────
    def _on_start_clicked(self):
        if self.start_callback:
            self.start_callback(mode="camera")

    def _on_mirror_clicked(self):
        if self.start_callback:
            self.start_callback(mode="mirror")

    def _on_stop_clicked(self):
        if self.stop_callback:
            self.stop_callback()

    def _on_install_clicked(self):
        if self.install_callback:
            self.btn_install.configure(state="disabled", text="Installing…")
            self.append_log("Starting installation process…")
            self.install_callback()

    def _on_setting_change(self, key, value):
        if self.setting_change_callback:
            self.setting_change_callback(key, value)
        if hasattr(self, "current_settings"):
            self.current_settings[key] = value
        if key in ("camera_device", "mirror_device"):
            self._update_statusbar_devices()

    def _on_target_dev_change(self, selected_value):
        serial = selected_value.split("(")[-1].strip(")")
        self._on_setting_change("target_device", serial)
        self.append_log(f"Target device changed to: {serial}")

    def _on_radio_target_change(self):
        serial = self.var_target_dev.get()
        self._on_setting_change("target_device", serial)

    def _on_camera_change(self, selected_value):
        camera_id = ""
        if selected_value != "Auto":
            camera_id = selected_value.replace("Camera ", "").split(" ")[0].strip()
        self._on_setting_change("last_camera", camera_id)
        self._sync_fps_options(camera_id)

    def _sync_fps_options(self, camera_id):
        fps_values = []
        for camera in self.camera_options:
            if camera.get("id") == camera_id:
                fps_values = camera.get("fps", [])
                break
        if not fps_values:
            fps_values = ["15", "24", "30"]
        self.opt_fps.configure(values=fps_values)
        if self.opt_fps.get() not in fps_values:
            best = fps_values[-1]
            self.opt_fps.set(best)
            self._on_setting_change("fps", int(best))

    def _on_browse_screenshot(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(title="Select Screenshot Directory")
        if path:
            self.var_screenshot_path.set(path)
            self._on_setting_change("screenshot_path", path)

    # ── window icon ───────────────────────────────────────────
    def _set_window_icon(self, window):
        from config.config import Config
        try:
            icon_ico = os.path.join(Config.APP_DIR, "icon", "app.ico")
            icon_png = os.path.join(Config.APP_DIR, "icon", "app.png")
            if os.name == "nt" and os.path.exists(icon_ico):
                if isinstance(window, ctk.CTkToplevel):
                    window.after(250, lambda: self._apply_ico_safe(window, icon_ico))
                else:
                    window.iconbitmap(icon_ico)
            elif os.path.exists(icon_png):
                import tkinter as tk
                img = tk.PhotoImage(file=icon_png)
                window.iconphoto(False, img)
        except Exception:
            pass

    def _apply_ico_safe(self, window, path):
        try:
            if window.winfo_exists():
                window.iconbitmap(path)
        except Exception:
            pass

    # ── compat stubs ──────────────────────────────────────────
    def _section(self, title, row): pass
    def _field(self, parent, label_text, widget, row, column, columnspan=1): pass
    def _rotate_to_label(self, value):
        v = {1: 90, 2: 180, 3: 270, "1": 90, "2": 180, "3": 270}.get(value, value)
        try: v = int(v)
        except: v = 0
        return f"{v} deg"
    def _rotate_from_label(self, value):
        try: return int(str(value).split()[0])
        except: return 0

    # ═══════════════════════════════════════════════════════════
    #  SCRCPY UPDATE DIALOG
    # ═══════════════════════════════════════════════════════════
    def show_scrcpy_update_prompt(self, local_ver, latest_ver, download_url, installer):
        from updater.installer_manager import UpdateDownloader
        dialog = ctk.CTkToplevel(self)
        dialog.title("scrcpy Update Available")
        dialog.geometry("460x280")
        dialog.resizable(False, False)
        dialog.transient(self); dialog.grab_set(); dialog.focus_set()
        dialog.configure(fg_color=T.BG_0)
        self._set_window_icon(dialog)
        px = self.winfo_x() + (self.winfo_width() - 460) // 2
        py = self.winfo_y() + (self.winfo_height() - 280) // 2
        dialog.geometry(f"460x280+{px}+{py}")

        c = ctk.CTkFrame(dialog, fg_color="transparent")
        c.pack(fill="both", expand=True, padx=24, pady=24)
        make_label(c, "scrcpy Update Available", size=15, weight="bold", color=T.TEXT_0).pack(anchor="w", pady=(0, 8))
        make_label(c, f"Installed:   v{local_ver}\nAvailable:  v{latest_ver}\n\nDownload and install now?",
                   size=12, color=T.TEXT_1).pack(anchor="w", pady=(0, 20))

        bf = ctk.CTkFrame(c, fg_color="transparent")
        bf.pack(fill="x", side="bottom")

        def on_later(): dialog.destroy()
        def on_update():
            for w in c.winfo_children(): w.destroy()
            make_label(c, "Downloading scrcpy…", size=14, weight="bold", color=T.TEXT_0).pack(anchor="w", pady=(0, 12))
            pb = ctk.CTkProgressBar(c, fg_color=T.BG_2, progress_color=T.AMBER, corner_radius=4)
            pb.pack(fill="x", pady=(0, 8)); pb.set(0)
            lbl_s = make_label(c, "Connecting…", size=11, color=T.TEXT_1)
            lbl_s.pack(anchor="w", pady=(0, 16))
            bf2 = ctk.CTkFrame(c, fg_color="transparent"); bf2.pack(fill="x", side="bottom")
            import logging
            downloader = UpdateDownloader(download_url, logging.getLogger("CameraStudio.download"))
            _paused = [False]
            def toggle_pause():
                if _paused[0]: downloader.resume(); _paused[0]=False; btn_p.configure(text="Pause")
                else: downloader.pause(); _paused[0]=True; btn_p.configure(text="Resume"); lbl_s.configure(text="Paused.")
            ctk.CTkButton(bf2, text="Cancel", width=90, height=34, fg_color="transparent",
                          border_width=1, border_color=T.BORDER, hover_color=T.RED,
                          text_color=T.TEXT_1, corner_radius=T.R_SM, command=downloader.cancel).pack(side="right")
            btn_p = ctk.CTkButton(bf2, text="Pause", width=90, height=34, fg_color=T.BG_2,
                                   hover_color=T.BG_3, text_color=T.TEXT_1, corner_radius=T.R_SM,
                                   command=toggle_pause)
            btn_p.pack(side="right", padx=(0, 8))
            def progress_cb(downloaded, total):
                ratio = downloaded/total if total > 0 else 0.5
                txt = (f"Downloaded {downloaded/1048576:.1f} / {total/1048576:.1f} MB  ({int(ratio*100)}%)"
                       if total > 0 else f"Downloaded {downloaded/1048576:.1f} MB")
                if not _paused[0]: dialog.after(0, lambda: [lbl_s.configure(text=txt), pb.set(ratio)])
            def completion_cb(status, dest_path):
                def update_ui():
                    if status == "Success":
                        for w in c.winfo_children(): w.destroy()
                        make_label(c, "Extracting…", size=14, weight="bold", color=T.TEXT_0).pack(anchor="w", pady=(0,12))
                        ext_bar = ctk.CTkProgressBar(c, fg_color=T.BG_2, progress_color=T.ORANGE,
                                                     corner_radius=4, mode="indeterminate")
                        ext_bar.pack(fill="x", pady=(0,8)); ext_bar.start()
                        def on_extract(result):
                            def show_result():
                                for w in c.winfo_children(): w.destroy()
                                if result == "Success":
                                    make_label(c, "✓  scrcpy Updated!", size=14, weight="bold", color=T.GREEN).pack(anchor="w", pady=(0,8))
                                    make_label(c, f"v{latest_ver} installed.", size=12, color=T.TEXT_1).pack(anchor="w", pady=(0,16))
                                    from config.config import Config
                                    self.update_dependency_status("scrcpy", Config.check_dependency("scrcpy"))
                                else:
                                    make_label(c, "Extraction Failed", size=14, weight="bold", color=T.RED).pack(anchor="w", pady=(0,8))
                                    make_label(c, str(result), size=11, color=T.TEXT_1).pack(anchor="w", pady=(0,12))
                                ctk.CTkButton(c, text="Close", width=90, height=34, fg_color=T.BG_2,
                                              hover_color=T.BG_3, text_color=T.TEXT_1, corner_radius=T.R_SM,
                                              command=dialog.destroy).pack(side="right")
                            dialog.after(0, show_result)
                        def run_extraction():
                            try:
                                import zipfile, shutil; from config.config import Config
                                scrcpy_dir = os.path.join(Config.BIN_DIR, "scrcpy")
                                temp_dir   = os.path.join(Config.CACHE_DIR, "scrcpy_update_extract")
                                if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
                                os.makedirs(temp_dir, exist_ok=True)
                                with zipfile.ZipFile(dest_path, "r") as zf: zf.extractall(temp_dir)
                                if os.path.exists(scrcpy_dir): shutil.rmtree(scrcpy_dir)
                                os.makedirs(scrcpy_dir, exist_ok=True)
                                items = os.listdir(temp_dir)
                                src = os.path.join(temp_dir, items[0]) if (len(items)==1 and os.path.isdir(os.path.join(temp_dir, items[0]))) else temp_dir
                                for x in os.listdir(src): shutil.move(os.path.join(src, x), os.path.join(scrcpy_dir, x))
                                shutil.rmtree(temp_dir, ignore_errors=True)
                                try: os.remove(dest_path)
                                except: pass
                                on_extract("Success")
                            except Exception as e: on_extract(str(e))
                        threading.Thread(target=run_extraction, daemon=True).start()
                    elif status == "Cancelled": dialog.destroy()
                    else:
                        for w in c.winfo_children(): w.destroy()
                        make_label(c, "Download Failed", size=14, weight="bold", color=T.RED).pack(anchor="w", pady=(0,8))
                        make_label(c, str(status), size=11, color=T.TEXT_1).pack(anchor="w", pady=(0,12))
                        ctk.CTkButton(c, text="Close", width=90, height=34, fg_color=T.BG_2,
                                      hover_color=T.BG_3, text_color=T.TEXT_1, corner_radius=T.R_SM,
                                      command=dialog.destroy).pack(side="right")
                dialog.after(0, update_ui)
            dialog.protocol("WM_DELETE_WINDOW", lambda: [downloader.cancel(), dialog.destroy()])
            downloader.start(progress_cb, completion_cb)

        ctk.CTkButton(bf, text="Later", width=90, height=34, fg_color="transparent",
                      border_width=1, border_color=T.BORDER, hover_color=T.BG_3,
                      text_color=T.TEXT_1, corner_radius=T.R_SM, command=on_later).pack(side="right")
        ctk.CTkButton(bf, text="Update Now", width=110, height=34, fg_color=T.AMBER,
                      hover_color=T.AMBER_H, text_color="#1A0A00", font=(T.FONT, 12, "bold"),
                      corner_radius=T.R_SM, command=on_update).pack(side="right", padx=(0, 8))

    # ═══════════════════════════════════════════════════════════
    #  SCRCPY ERROR DIALOG
    # ═══════════════════════════════════════════════════════════
    def show_scrcpy_error_dialog(self, mode, exit_code, last_lines):
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"scrcpy {mode.capitalize()} Error")
        dialog.geometry("520x420")
        dialog.resizable(False, False)
        dialog.transient(self); dialog.grab_set(); dialog.focus_set()
        dialog.configure(fg_color=T.BG_0)
        self._set_window_icon(dialog)
        px = self.winfo_x() + (self.winfo_width() - 520) // 2
        py = self.winfo_y() + (self.winfo_height() - 420) // 2
        dialog.geometry(f"520x420+{px}+{py}")

        c = ctk.CTkFrame(dialog, fg_color="transparent")
        c.pack(fill="both", expand=True, padx=24, pady=24)
        hdr = ctk.CTkFrame(c, fg_color="transparent"); hdr.pack(fill="x", pady=(0, 12))
        make_label(hdr, "⚠", size=22).pack(side="left", padx=(0, 10))
        make_label(hdr, f"scrcpy {mode.capitalize()} Stopped Unexpectedly",
                   size=14, weight="bold", color=T.RED).pack(side="left", anchor="center")
        make_label(c, f"Exit code: {exit_code}", size=11, weight="bold", color=T.TEXT_1).pack(anchor="w", pady=(0, 6))
        make_label(c, "Console Output:", size=10, color=T.TEXT_2).pack(anchor="w", pady=(0, 4))
        txt = ctk.CTkTextbox(c, height=120, wrap="word", fg_color=T.BG_1, text_color=T.TEXT_0,
                              font=(T.MONO, 10), corner_radius=T.R_SM, border_width=1, border_color=T.BORDER)
        txt.pack(fill="both", expand=True, pady=(0, 12))
        txt.insert("1.0", "\n".join(last_lines) if last_lines else "No output.")
        txt.configure(state="disabled")
        log_lower = ("\n".join(last_lines)).lower()
        if any(k in log_lower for k in ["symbol lookup", "libpango", "fontconfig"]):
            advice = "Linux library mismatch.\nRun: sudo apt update && sudo apt upgrade"
        elif any(k in log_lower for k in ["device not found", "waiting for device"]):
            advice = "Connection issue.\nReconnect USB, enable USB Debugging, authorize on device."
        elif any(k in log_lower for k in ["audio", "codec"]):
            advice = "Audio/Codec issue.\nTry changing Audio Source to 'Off'."
        else:
            advice = "Ensure device is unlocked and correct serial / camera ID is selected."
        tip_card = ctk.CTkFrame(c, fg_color=T.BG_2, corner_radius=T.R_SM)
        tip_card.pack(fill="x", pady=(0, 16))
        make_label(tip_card, "💡  " + advice, size=11, color=T.TEXT_1).pack(anchor="w", padx=12, pady=8)
        ctk.CTkButton(c, text="Dismiss", width=100, height=34, fg_color=T.RED, hover_color="#C0392B",
                      text_color=T.TEXT_0, font=(T.FONT, 12, "bold"), corner_radius=T.R_SM,
                      command=dialog.destroy).pack(side="right")


# ═══════════════════════════════════════════════════════════════
#  MIRROR CONTROL FLOATING PANEL
# ═══════════════════════════════════════════════════════════════
class MirrorControlCenter(ctk.CTkToplevel):
    def __init__(self, parent, scrcpy_manager):
        super().__init__(parent)
        self.parent = parent
        self.scrcpy_manager = scrcpy_manager
        self.overrideredirect(True)
        self.title("Mirror Control")
        self.geometry("64x420")
        self.attributes("-alpha", 0.96)
        px = parent.winfo_x(); py = parent.winfo_y(); pw = parent.winfo_width()
        self.geometry(f"64x420+{px + pw + 10}+{py}")
        self._last_ctrl_x  = None; self._last_ctrl_y  = None
        self._last_scrcpy_x = None; self._last_scrcpy_y = None
        self._setup_ui()
        self.update(); self.attributes("-topmost", True)
        for w in (self, getattr(self, "bg_frame", None), getattr(self, "container", None)):
            if w:
                w.bind("<Button-1>", self._start_drag)
                w.bind("<B1-Motion>", self._on_drag)
        self._track_scrcpy_window()

    def _start_drag(self, event):
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def _on_drag(self, event):
        self.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")

    def _setup_ui(self):
        self.is_collapsed = False; self.control_buttons = []
        self.bg_frame = ctk.CTkFrame(self, fg_color=T.BG_1, border_width=1,
                                      border_color=T.BORDER, corner_radius=T.R_SM)
        self.bg_frame.pack(fill="both", expand=True)
        self.container = ctk.CTkFrame(self.bg_frame, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=4, pady=4)
        self.btn_toggle = ctk.CTkButton(self.container, text="▶", width=46, height=24,
                                         font=(T.FONT, 11, "bold"), fg_color=T.BG_2,
                                         hover_color=T.BG_3, text_color=T.TEXT_1,
                                         corner_radius=T.R_SM, command=self._toggle_collapse)
        self.btn_toggle.pack(pady=(2, 6), padx=2)
        for icon, label, cmd, tip in [
            ("🏠", "Home",    self._press_home,        "Go Home"),
            ("🔙", "Back",    self._press_back,        "Go Back"),
            ("⏻",  "Power",   self._press_power,       "Toggle Power"),
            ("🔊", "Vol +",   self._press_volume_up,   "Volume Up"),
            ("🔉", "Vol −",   self._press_volume_down, "Volume Down"),
            ("🔄", "Rotate",  self._toggle_rotation,   "Toggle Rotation"),
            ("📸", "Capture", self._take_screenshot,   "Take Screenshot"),
            ("✕",  "Stop",    self._stop_mirror,       "Stop Mirror"),
        ]:
            is_stop = (label == "Stop")
            btn = ctk.CTkButton(self.container, text=icon, width=46, height=36,
                                 font=(T.FONT, 14),
                                 fg_color=T.RED if is_stop else T.BG_2,
                                 hover_color="#C0392B" if is_stop else T.BG_3,
                                 text_color=T.TEXT_0, corner_radius=T.R_SM, command=cmd)
            btn.pack(pady=3, padx=2)
            self.control_buttons.append(btn)
            ToolTip(btn, f"{label}\n{tip}")

    def _toggle_collapse(self):
        self.is_collapsed = not self.is_collapsed
        if self.is_collapsed:
            self.btn_toggle.configure(text="◀")
            for btn in self.control_buttons: btn.pack_forget()
            self.container.pack_configure(padx=1, pady=4)
            self.btn_toggle.configure(width=12, height=380)
            self.geometry("20x420")
        else:
            self.btn_toggle.configure(text="▶", width=46, height=24)
            self.container.pack_configure(padx=4, pady=4)
            for btn in self.control_buttons: btn.pack(pady=3, padx=2)
            self.geometry("64x420")

    def _serial(self):
        serial = getattr(self.parent, "current_settings", {}).get("mirror_device", "")
        if not serial:
            serial = self.parent.var_target_dev.get().split("(")[-1].strip(")")
        return serial

    def _adb(self, *extra):
        import subprocess; from config.config import Config
        from services.scrcpy_manager import get_clean_subprocess_env
        serial = self._serial()
        cmd = [Config.get_bin_path("adb")] + (["-s", serial] if serial else []) + list(extra)
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        env = get_clean_subprocess_env()
        subprocess.run(cmd, creationflags=flags, env=env, timeout=5)

    def _execute_adb_key(self, code):
        threading.Thread(target=lambda: self._adb("shell", "input", "keyevent", str(code)), daemon=True).start()

    def _press_home(self):        self._execute_adb_key(3)
    def _press_back(self):        self._execute_adb_key(4)
    def _press_power(self):       self._execute_adb_key(26)
    def _press_volume_up(self):   self._execute_adb_key(24)
    def _press_volume_down(self): self._execute_adb_key(25)

    def _toggle_rotation(self):
        def worker():
            try:
                import subprocess; from config.config import Config
                from services.scrcpy_manager import get_clean_subprocess_env
                serial = self._serial()
                adb = Config.get_bin_path("adb")
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                env = get_clean_subprocess_env()
                cmd_get = [adb] + (["-s", serial] if serial else []) + ["shell", "settings", "get", "system", "user_rotation"]
                out = subprocess.check_output(cmd_get, text=True, stderr=subprocess.DEVNULL, env=env).strip()
                next_rot = (int(out) if out.isdigit() else 0 + 1) % 4
                cmd_set = [adb] + (["-s", serial] if serial else []) + ["shell", "settings", "put", "system", "user_rotation", str(next_rot)]
                subprocess.run(cmd_set, creationflags=flags, env=env, timeout=5)
            except Exception: pass
        threading.Thread(target=worker, daemon=True).start()

    def _take_screenshot(self):
        def worker():
            try:
                import subprocess, time; from config.config import Config
                from services.scrcpy_manager import get_clean_subprocess_env
                adb = Config.get_bin_path("adb"); serial = self._serial()
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                env = get_clean_subprocess_env()
                settings = getattr(self.parent, "current_settings", {})
                ss_dir = settings.get("screenshot_path", "") or os.path.join(os.path.expanduser("~"), "Pictures", "scrcpy_studio")
                os.makedirs(ss_dir, exist_ok=True)
                fname = f"screenshot_{int(time.time())}.png"
                local = os.path.join(ss_dir, fname); remote = f"/sdcard/{fname}"
                s = ["-s", serial] if serial else []
                for cmd in [
                    [adb] + s + ["shell", "screencap", "-p", remote],
                    [adb] + s + ["pull", remote, local],
                    [adb] + s + ["shell", "rm", remote],
                ]: subprocess.run(cmd, creationflags=flags, env=env, timeout=8)
                self.parent.after(0, lambda: self.parent.append_log(f"Screenshot saved: {local}"))
            except Exception as e:
                self.parent.after(0, lambda: self.parent.append_log(f"Screenshot failed: {e}"))
        self.parent.append_log("Capturing screenshot…")
        threading.Thread(target=worker, daemon=True).start()

    def _stop_mirror(self):
        self.scrcpy_manager.stop("mirror")
        self.destroy()

    def _track_scrcpy_window(self):
        if not self.winfo_exists(): return
        if not hasattr(self, "_start_time"):
            import time; self._start_time = time.time()
        import time
        if time.time() - self._start_time > 5.0 and not self.scrcpy_manager.is_running("mirror"):
            self.destroy(); return
        try:
            import subprocess, re
            sx = sy = sw = None
            if os.name == "nt":
                try:
                    import ctypes; user32 = ctypes.windll.user32
                    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                    found = ctypes.c_void_p(0)
                    def cb(hwnd, lp):
                        n = user32.GetWindowTextLengthW(hwnd)
                        if n > 0:
                            b = ctypes.create_unicode_buffer(n+1); user32.GetWindowTextW(hwnd, b, n+1)
                            if "scrcpy_mirror" in b.value:
                                ctypes.cast(lp, ctypes.POINTER(ctypes.c_void_p))[0] = hwnd; return False
                        return True
                    user32.EnumWindows(WNDENUMPROC(cb), ctypes.cast(ctypes.byref(found), ctypes.c_void_p))
                    hwnd = found.value
                    if hwnd:
                        rect = ctypes.wintypes.RECT()
                        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                            sx, sy, sw = rect.left, rect.top, rect.right - rect.left
                except Exception: pass
            else:
                try:
                    ids = [l.strip() for l in subprocess.check_output(["xdotool", "search", "--name", "scrcpy_mirror"], text=True, stderr=subprocess.DEVNULL).splitlines() if l.strip()]
                    if ids:
                        info = subprocess.check_output(["xwininfo", "-id", ids[0]], text=True, stderr=subprocess.DEVNULL)
                        mx = re.search(r"Absolute upper-left X:\s+(-?\d+)", info)
                        my = re.search(r"Absolute upper-left Y:\s+(-?\d+)", info)
                        mw = re.search(r"Width:\s+(\d+)", info)
                        if mx and my and mw: sx, sy, sw = int(mx.group(1)), int(my.group(1)), int(mw.group(1))
                except Exception:
                    try:
                        for line in subprocess.check_output(["wmctrl", "-lG"], text=True, stderr=subprocess.DEVNULL).splitlines():
                            if "scrcpy_mirror" in line:
                                p = line.split()
                                if len(p) >= 6: sx, sy, sw = int(p[2]), int(p[3]), int(p[4]); break
                    except Exception: pass
            if sx is not None and sy is not None:
                cx, cy = self.winfo_x(), self.winfo_y()
                if self._last_ctrl_x is None:
                    nx, ny = sx + sw + 1, sy; self.geometry(f"+{nx}+{ny}")
                    self._last_ctrl_x, self._last_ctrl_y = nx, ny
                    self._last_scrcpy_x, self._last_scrcpy_y = sx, sy
                elif abs(cx - self._last_ctrl_x) > 1 or abs(cy - self._last_ctrl_y) > 1:
                    self._last_ctrl_x, self._last_ctrl_y = cx, cy
                    self._last_scrcpy_x, self._last_scrcpy_y = sx, sy
                elif abs(sx - self._last_scrcpy_x) > 1 or abs(sy - self._last_scrcpy_y) > 1:
                    nx, ny = sx + sw + 1, sy; self.geometry(f"+{nx}+{ny}")
                    self._last_ctrl_x, self._last_ctrl_y = nx, ny
                    self._last_scrcpy_x, self._last_scrcpy_y = sx, sy
                else:
                    self._last_ctrl_x, self._last_ctrl_y = cx, cy
                    self._last_scrcpy_x, self._last_scrcpy_y = sx, sy
        except Exception: pass
        self.after(200, self._track_scrcpy_window)


# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = CameraStudioUI()
    app.apply_theme("Dark")
    app.append_log("Application initialized successfully.")
    app.mainloop()

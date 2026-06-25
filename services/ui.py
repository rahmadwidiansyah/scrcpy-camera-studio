import customtkinter as ctk
import threading
import os
from updater.installer_manager import UpdateDownloader


class CameraStudioUI(ctk.CTk):
    def report_callback_exception(self, exc, val, tb):
        import logging
        err_logger = logging.getLogger("CameraStudio.exception")
        err_logger.error("Uncaught exception in GUI callback", exc_info=(exc, val, tb))

    def __init__(self):
        super().__init__()

        from config.version import current_version
        self.current_version = current_version
        self.title(f"Camera Studio v{current_version}")
        self.geometry("760x760")
        self.minsize(680, 620)

        self.start_callback = None
        self.stop_callback = None
        self.setting_change_callback = None
        self.install_callback = None

        self.status_labels = {}
        self.device_rows = []
        self.camera_options = []
        self._scrcpy_running_ui = False
        self._ui_thread_id = threading.get_ident()
        self.update_result = None

        self._setup_ui()

    def set_callbacks(self, start_cb, stop_cb, setting_change_cb, install_cb):
        self.start_callback = start_cb
        self.stop_callback = stop_cb
        self.setting_change_callback = setting_change_cb
        self.install_callback = install_cb

    def apply_theme(self, theme_name):
        if theme_name:
            ctk.set_appearance_mode(theme_name)

    def load_settings_to_ui(self, settings_data):
        cam_id = settings_data.get("last_camera", "")
        self.opt_cam.set(f"Camera {cam_id}" if cam_id else "Auto")
        self.opt_res.set(str(settings_data.get("resolution", "1080")))
        self.opt_fps.set(str(settings_data.get("fps", 30)))
        self.opt_bit.set(str(settings_data.get("bitrate", "8M")))
        self.opt_rot.set(self._rotate_to_label(settings_data.get("rotate", 0)))
        self.opt_preview.set(str(settings_data.get("preview_mode", "Normal Window")))

        self.chk_audio.select() if settings_data.get("audio", False) else self.chk_audio.deselect()
        self.chk_mirror.select() if settings_data.get("mirror", False) else self.chk_mirror.deselect()

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

    def _setup_ui(self):
        self.configure(fg_color=("#f4f6f8", "#111318"))

        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=16, pady=16)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(4, weight=1)

        self._build_header()
        self._build_dependencies()
        self._build_devices()
        self._build_controls()
        self._build_log()

    def _build_header(self):
        header = ctk.CTkFrame(self.main_frame, corner_radius=8)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(0, weight=1)

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w", padx=14, pady=12)

        title_row = ctk.CTkFrame(title_box, fg_color="transparent")
        title_row.pack(anchor="w")

        ctk.CTkLabel(title_row, text="Camera Studio", font=("Arial", 20, "bold")).pack(side="left")
        
        self.badge_update = ctk.CTkLabel(
            title_row,
            text="🔴 Update",
            font=("Arial", 10, "bold"),
            text_color="#ffffff",
            fg_color="#dc3545",
            corner_radius=8,
            height=18,
            cursor="hand2"
        )
        # Badge click event binding is handled externally by UpdatePresenter

        self.lbl_cam_status = ctk.CTkLabel(
            title_box,
            text="Stopped",
            text_color="#dc3545",
            font=("Arial", 13, "bold")
        )
        self.lbl_cam_status.pack(anchor="w", pady=(2, 0))

        button_box = ctk.CTkFrame(header, fg_color="transparent")
        button_box.grid(row=0, column=1, sticky="e", padx=14, pady=12)

        self.btn_start = ctk.CTkButton(
            button_box,
            text="Start Camera",
            width=120,
            height=38,
            fg_color="#198754",
            hover_color="#157347",
            command=self._on_start_clicked
        )
        self.btn_start.pack(side="left", padx=(0, 6))

        self.btn_mirror = ctk.CTkButton(
            button_box,
            text="Screen Mirror",
            width=120,
            height=38,
            fg_color="#0d6efd",
            hover_color="#0b5ed7",
            command=self._on_mirror_clicked
        )
        self.btn_mirror.pack(side="left", padx=(0, 6))

        self.btn_stop = ctk.CTkButton(
            button_box,
            text="Stop",
            width=80,
            height=38,
            fg_color="#dc3545",
            hover_color="#bb2d3b",
            state="disabled",
            command=self._on_stop_clicked
        )
        self.btn_stop.pack(side="left")

    def _build_dependencies(self):
        frame = self._section("System Check", 1)
        for index, dep_name in enumerate(("adb", "scrcpy", "SDL2", "ffmpeg")):
            label = ctk.CTkLabel(frame, text=f"{dep_name.upper()}: Checking", anchor="w")
            label.grid(row=1, column=index, sticky="ew", padx=8, pady=(0, 10))
            frame.grid_columnconfigure(index, weight=1)
            self.status_labels[dep_name] = label

        self.btn_install = ctk.CTkButton(
            frame,
            text="Install Missing Dependencies",
            fg_color="#0d6efd",
            hover_color="#0b5ed7",
            command=self._on_install_clicked
        )

    def _build_devices(self):
        frame = self._section("Device", 2)
        frame.grid_columnconfigure(0, weight=1)

        self.list_container = ctk.CTkFrame(frame, fg_color="transparent")
        self.list_container.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.list_container.grid_columnconfigure(0, weight=1)

        self.lbl_no_device = ctk.CTkLabel(
            self.list_container,
            text="No device detected",
            anchor="w",
            text_color=("#59636e", "#b8c0cc")
        )
        self.lbl_no_device.grid(row=0, column=0, sticky="ew", pady=4)

        self.target_dev_frame = ctk.CTkFrame(frame, fg_color="transparent")
        self.target_dev_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.target_dev_frame, text="Target", width=80, anchor="w").grid(
            row=0, column=0, padx=(8, 10), pady=(0, 10), sticky="w"
        )
        self.var_target_dev = ctk.StringVar()
        self.opt_target_dev = ctk.CTkOptionMenu(
            self.target_dev_frame,
            variable=self.var_target_dev,
            command=self._on_target_dev_change
        )
        self.opt_target_dev.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(0, 10))

    def _build_controls(self):
        frame = self._section("Camera Settings", 3)
        for column in range(4):
            frame.grid_columnconfigure(column, weight=1)

        self.var_cam = ctk.StringVar()
        self.opt_cam = ctk.CTkOptionMenu(
            frame,
            values=["Auto"],
            variable=self.var_cam,
            command=self._on_camera_change
        )
        self._field(frame, "Camera", self.opt_cam, 1, 0)

        self.opt_res = ctk.CTkOptionMenu(
            frame,
            values=["720", "1080", "1920", "Auto"],
            command=lambda value: self._on_setting_change("resolution", value)
        )
        self._field(frame, "Resolution", self.opt_res, 1, 1)

        self.opt_fps = ctk.CTkOptionMenu(
            frame,
            values=["15", "24", "30"],
            command=lambda value: self._on_setting_change("fps", int(value))
        )
        self._field(frame, "FPS", self.opt_fps, 1, 2)

        self.opt_bit = ctk.CTkOptionMenu(
            frame,
            values=["4M", "8M", "16M", "24M"],
            command=lambda value: self._on_setting_change("bitrate", value)
        )
        self._field(frame, "Bitrate", self.opt_bit, 1, 3)

        self.opt_rot = ctk.CTkOptionMenu(
            frame,
            values=["0 deg", "90 deg", "180 deg", "270 deg"],
            command=lambda value: self._on_setting_change("rotate", self._rotate_from_label(value))
        )
        self._field(frame, "Rotate", self.opt_rot, 3, 0)

        self.opt_preview = ctk.CTkOptionMenu(
            frame,
            values=["Normal Window", "Borderless", "Always On Top", "Hidden Preview"],
            command=lambda value: self._on_setting_change("preview_mode", value)
        )
        self._field(frame, "Preview", self.opt_preview, 3, 1, columnspan=2)

        switch_box = ctk.CTkFrame(frame, fg_color="transparent")
        switch_box.grid(row=4, column=3, sticky="ew", padx=8, pady=(0, 12))
        self.chk_audio = ctk.CTkCheckBox(
            switch_box,
            text="Audio",
            command=lambda: self._on_setting_change("audio", bool(self.chk_audio.get()))
        )
        self.chk_audio.pack(side="left", padx=(0, 12))

        self.chk_mirror = ctk.CTkCheckBox(
            switch_box,
            text="Mirror",
            command=lambda: self._on_setting_change("mirror", bool(self.chk_mirror.get()))
        )
        self.chk_mirror.pack(side="left")

    def _build_log(self):
        frame = self._section("Log", 4)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        self.txt_log = ctk.CTkTextbox(
            frame,
            state="disabled",
            wrap="word",
            height=180,
            fg_color="#111318",
            text_color="#f2f2f2"
        )
        self.txt_log.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 10))
        try:
            self.txt_log.tag_config("normal", foreground="#f2f2f2")
            self.txt_log.tag_config("error", foreground="#ff5f6d")
        except Exception:
            pass

    def _section(self, title, row):
        frame = ctk.CTkFrame(self.main_frame, corner_radius=8)
        frame.grid(row=row, column=0, sticky="ew" if row != 4 else "nsew", pady=(0, 10))
        ctk.CTkLabel(frame, text=title, font=("Arial", 14, "bold"), anchor="w").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 8)
        )
        return frame

    def _field(self, parent, label_text, widget, row, column, columnspan=1):
        ctk.CTkLabel(parent, text=label_text, anchor="w").grid(
            row=row, column=column, columnspan=columnspan, sticky="w", padx=8, pady=(0, 4)
        )
        widget.grid(
            row=row + 1,
            column=column,
            columnspan=columnspan,
            sticky="ew",
            padx=8,
            pady=(0, 12)
        )

    def _on_setting_change(self, key, value):
        if self.setting_change_callback:
            self.setting_change_callback(key, value)

    def _on_target_dev_change(self, selected_value):
        serial = selected_value.split("(")[-1].strip(")")
        self._on_setting_change("target_device", serial)
        self.append_log(f"Target device changed to: {serial}")

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
        current_fps = self.opt_fps.get()
        if current_fps not in fps_values:
            best_fps = fps_values[-1]
            self.opt_fps.set(best_fps)
            self._on_setting_change("fps", int(best_fps))

    def update_camera_options(self, cameras):
        self.camera_options = cameras
        options = ["Auto"] + [camera["label"] for camera in cameras]
        self.opt_cam.configure(values=options)

        current_id = self.var_cam.get().replace("Camera ", "").split(" ")[0].strip()
        selected = "Auto"
        for camera in cameras:
            if camera["id"] == current_id:
                selected = camera["label"]
                break

        if selected == "Auto" and cameras:
            selected = cameras[0]["label"]

        self.opt_cam.set(selected)
        self._on_camera_change(selected)

    def update_device_list(self, devices):
        for row in self.device_rows:
            row.destroy()
        self.device_rows.clear()

        if not devices:
            self.lbl_no_device.grid(row=0, column=0, sticky="ew", pady=4)
            self.target_dev_frame.grid_forget()
            self._on_setting_change("target_device", "")
            return

        self.lbl_no_device.grid_forget()
        ready_devices = []

        for index, dev in enumerate(devices):
            row_frame = ctk.CTkFrame(self.list_container, fg_color="transparent")
            row_frame.grid(row=index, column=0, sticky="ew", pady=2)
            row_frame.grid_columnconfigure(0, weight=1)
            self.device_rows.append(row_frame)

            model_name = getattr(dev, "model_name", "Unknown")
            serial_num = getattr(dev, "serial", "Unknown")
            status = getattr(dev, "status", "unknown")

            if status == "device":
                status_text = "Ready"
                status_color = "#28a745"
                ready_devices.append(dev)
            elif status == "unauthorized":
                status_text = "Unauthorized"
                status_color = "#dc3545"
            else:
                status_text = status.capitalize()
                status_color = "#ffc107"

            ctk.CTkLabel(row_frame, text=f"{model_name}  ({serial_num})", anchor="w").grid(
                row=0, column=0, sticky="ew"
            )
            ctk.CTkLabel(row_frame, text=status_text, text_color=status_color, width=110, anchor="e").grid(
                row=0, column=1, sticky="e"
            )

        if len(ready_devices) > 1:
            self.target_dev_frame.grid(row=2, column=0, sticky="ew")
            options = [
                f"{getattr(device, 'model_name', 'Unknown')} ({getattr(device, 'serial', 'Unknown')})"
                for device in ready_devices
            ]
            self.opt_target_dev.configure(values=options)
            if self.var_target_dev.get() not in options:
                self.opt_target_dev.set(options[0])
                self._on_target_dev_change(options[0])
        else:
            self.target_dev_frame.grid_forget()
            target_serial = getattr(ready_devices[0], "serial", "") if ready_devices else ""
            self._on_setting_change("target_device", target_serial)

    def set_camera_state(self, is_running):
        # Backward compatibility helper
        if isinstance(is_running, bool):
            statuses = {"camera": is_running, "mirror": False}
        else:
            statuses = is_running

        cam_running = statuses.get("camera", False)
        mir_running = statuses.get("mirror", False)

        # Update status labels / buttons
        if cam_running and mir_running:
            self.lbl_cam_status.configure(text="Camera & Mirror Running", text_color="#28a745")
        elif cam_running:
            self.lbl_cam_status.configure(text="Camera Running", text_color="#28a745")
        elif mir_running:
            self.lbl_cam_status.configure(text="Mirror Running", text_color="#28a745")
        else:
            self.lbl_cam_status.configure(text="Stopped", text_color="#dc3545")

        self.btn_start.configure(state="disabled" if cam_running else "normal")
        self.btn_mirror.configure(state="disabled" if mir_running else "normal")
        self.btn_stop.configure(state="normal" if (cam_running or mir_running) else "disabled")

        # Logging transitions
        if not hasattr(self, "_prev_statuses"):
            self._prev_statuses = {"camera": False, "mirror": False}
        
        if cam_running != self._prev_statuses.get("camera", False):
            self.append_log("Camera stream started." if cam_running else "Camera stream stopped.")
        if mir_running != self._prev_statuses.get("mirror", False):
            self.append_log("Mirror stream started." if mir_running else "Mirror stream stopped.")

        self._prev_statuses = {"camera": cam_running, "mirror": mir_running}
        self._scrcpy_running_ui = cam_running or mir_running

    def update_scrcpy_status(self, is_running):
        self.set_camera_state(is_running)

    def show_update_badge(self, show=True):
        if show:
            self.badge_update.pack(side="left", padx=(8, 0))
        else:
            self.badge_update.pack_forget()

    def handle_update_result(self, result):
        self.update_result = result
        is_available = result.get("is_update_available", False)
        self.show_update_badge(is_available)



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
            self.btn_install.configure(state="disabled", text="Installing...")
            self.append_log("Starting installation process...")
            self.install_callback()

    def show_installer_flow(self, is_missing):
        if is_missing:
            self.btn_install.grid(row=2, column=0, columnspan=4, sticky="ew", padx=8, pady=(0, 10))
            self.btn_start.configure(state="disabled")
            self.btn_mirror.configure(state="disabled")
            self.append_log("Action required: Missing dependencies detected.")
        else:
            self.btn_install.grid_forget()
            if not self._scrcpy_running_ui:
                self.btn_start.configure(state="normal")
                self.btn_mirror.configure(state="normal")

    def update_dependency_status(self, dep_name, is_found, is_optional=False):
        label = self.status_labels.get(dep_name)
        if not label:
            return

        if is_found:
            label.configure(text=f"{dep_name.upper()}: Found", text_color="#28a745")
            self.append_log(f"Dependency check: {dep_name.upper()} is ready.")
            return

        text = f"{dep_name.upper()}: Missing"
        color = "#ffc107" if is_optional else "#dc3545"
        if is_optional:
            text += " (Optional)"
            self.append_log(f"Dependency check: {dep_name.upper()} is missing (optional).")
        else:
            self.append_log(f"Error: Required dependency {dep_name.upper()} is missing.")
        label.configure(text=text, text_color=color)

    def show_scrcpy_update_prompt(self, local_ver, latest_ver, download_url, installer):
        dialog = ctk.CTkToplevel(self)
        dialog.title("scrcpy Update Available")
        dialog.geometry("450x300")
        dialog.resizable(False, False)

        dialog.transient(self)
        dialog.grab_set()
        dialog.focus_set()

        # Center dialog
        parent_x = self.winfo_x()
        parent_y = self.winfo_y()
        parent_w = self.winfo_width()
        parent_h = self.winfo_height()
        x = parent_x + (parent_w - 450) // 2
        y = parent_y + (parent_h - 300) // 2
        dialog.geometry(f"450x300+{x}+{y}")

        container = ctk.CTkFrame(dialog, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        lbl_title = ctk.CTkLabel(
            container, 
            text="scrcpy Update Available!", 
            font=("Arial", 16, "bold")
        )
        lbl_title.pack(anchor="w", pady=(0, 10))

        lbl_msg = ctk.CTkLabel(
            container, 
            text=f"A new version of scrcpy is available.\n\nInstalled Version:  {local_ver}\nLatest Version:     {latest_ver}\n\nWould you like to download and update scrcpy now?", 
            font=("Arial", 12),
            justify="left",
            anchor="w"
        )
        lbl_msg.pack(anchor="w", pady=(0, 20))

        btn_frame = ctk.CTkFrame(container, fg_color="transparent")
        btn_frame.pack(fill="x", side="bottom")

        def on_later():
            dialog.destroy()

        def on_update():
            # Clear container to render download progress
            for child in container.winfo_children():
                child.destroy()

            lbl_dl_title = ctk.CTkLabel(
                container, 
                text="Downloading scrcpy update...", 
                font=("Arial", 16, "bold")
            )
            lbl_dl_title.pack(anchor="w", pady=(0, 15))

            progress_bar = ctk.CTkProgressBar(container)
            progress_bar.pack(fill="x", pady=(0, 8))
            progress_bar.set(0.0)

            lbl_status = ctk.CTkLabel(
                container, 
                text="Connecting to download server...", 
                font=("Arial", 12),
                anchor="w"
            )
            lbl_status.pack(anchor="w", pady=(0, 20))

            btn_dl_frame = ctk.CTkFrame(container, fg_color="transparent")
            btn_dl_frame.pack(fill="x", side="bottom")

            import logging
            scrcpy_dl_logger = logging.getLogger("CameraStudio.download")
            scrcpy_dl_logger.info(f"Memulai unduhan update scrcpy dari: {download_url}")
            downloader = UpdateDownloader(download_url, scrcpy_dl_logger)
            is_currently_paused = False

            def toggle_pause():
                nonlocal is_currently_paused
                if is_currently_paused:
                    downloader.resume()
                    is_currently_paused = False
                    btn_pause.configure(text="Pause", fg_color=None, border_width=1, text_color=("#111318", "#f2f2f2"))
                    lbl_dl_title.configure(text="Downloading scrcpy update...")
                else:
                    downloader.pause()
                    is_currently_paused = True
                    btn_pause.configure(text="Resume", fg_color="#198754", hover_color="#157347", border_width=0, text_color="#ffffff")
                    lbl_dl_title.configure(text="Downloading Paused")
                    lbl_status.configure(text="Download paused by user.")

            btn_cancel = ctk.CTkButton(
                btn_dl_frame,
                text="Cancel",
                width=100,
                fg_color="transparent",
                hover_color=("#dc3545", "#dc3545"),
                border_width=1,
                text_color=("#111318", "#f2f2f2"),
                command=downloader.cancel
            )
            btn_cancel.pack(side="right")

            btn_pause = ctk.CTkButton(
                btn_dl_frame,
                text="Pause",
                width=100,
                fg_color="transparent",
                hover_color=("#e0e0e0", "#2a2a2a"),
                border_width=1,
                text_color=("#111318", "#f2f2f2"),
                command=toggle_pause
            )
            btn_pause.pack(side="right", padx=(0, 10))

            def progress_cb(downloaded, total):
                if total > 0:
                    pct = int((downloaded / total) * 100)
                    dl_mb = downloaded / (1024 * 1024)
                    tot_mb = total / (1024 * 1024)
                    status_text = f"Downloaded {dl_mb:.2f} MB of {tot_mb:.2f} MB ({pct}%)"
                    ratio = downloaded / total
                else:
                    dl_mb = downloaded / (1024 * 1024)
                    status_text = f"Downloaded {dl_mb:.2f} MB"
                    ratio = 0.5

                if not is_currently_paused:
                    dialog.after(0, lambda: lbl_status.configure(text=status_text))
                    dialog.after(0, lambda: progress_bar.set(ratio))

            def completion_cb(status, dest_path):
                if self.logger:
                    if status == "Success":
                        self.logger.info(f"Pembaruan scrcpy sukses diunduh ke: {dest_path}")
                    elif status == "Cancelled":
                        self.logger.info("Unduhan pembaruan scrcpy dibatalkan.")
                    else:
                        self.logger.error(f"Unduhan pembaruan scrcpy gagal: {status}")

                def update_ui():
                    if status == "Success":
                        # Render extraction view
                        for child in container.winfo_children():
                            child.destroy()

                        lbl_ext_title = ctk.CTkLabel(
                            container, 
                            text="Extracting scrcpy...", 
                            font=("Arial", 16, "bold")
                        )
                        lbl_ext_title.pack(anchor="w", pady=(0, 15))

                        ext_bar = ctk.CTkProgressBar(container)
                        ext_bar.pack(fill="x", pady=(0, 8))
                        ext_bar.configure(mode="indeterminate")
                        ext_bar.start()

                        lbl_ext_status = ctk.CTkLabel(
                            container, 
                            text="Extracting new binaries to runtime/scrcpy...", 
                            font=("Arial", 12),
                            anchor="w"
                        )
                        lbl_ext_status.pack(anchor="w", pady=(0, 20))

                        def on_extract_complete(result_status):
                            if self.logger:
                                if result_status == "Success":
                                    self.logger.info("Ekstraksi pembaruan scrcpy berhasil.")
                                else:
                                    self.logger.error(f"Ekstraksi pembaruan scrcpy gagal: {result_status}")
                            def show_extract_result():
                                for child in container.winfo_children():
                                    child.destroy()

                                if result_status == "Success":
                                    lbl_success = ctk.CTkLabel(
                                        container, 
                                        text="scrcpy Updated Successfully!", 
                                        font=("Arial", 16, "bold"),
                                        text_color="#28a745"
                                    )
                                    lbl_success.pack(anchor="w", pady=(0, 15))

                                    lbl_desc = ctk.CTkLabel(
                                        container, 
                                        text=f"The new scrcpy v{latest_ver} binary has been successfully installed in runtime/scrcpy.", 
                                        font=("Arial", 12),
                                        justify="left",
                                        wrap=400
                                    )
                                    lbl_desc.pack(anchor="w", pady=(0, 20))

                                    btn_ok = ctk.CTkButton(
                                        container,
                                        text="Close",
                                        width=100,
                                        fg_color="#0d6efd",
                                        hover_color="#0b5ed7",
                                        command=dialog.destroy
                                    )
                                    btn_ok.pack(side="right")

                                    # Update UI dependency statuses on main screen!
                                    from config.config import Config
                                    self.update_dependency_status("scrcpy", Config.check_dependency("scrcpy"))
                                    self.update_dependency_status("adb", Config.check_dependency("adb"))
                                    self.update_dependency_status("SDL2", Config.check_dependency("sdl2"))
                                else:
                                    lbl_fail = ctk.CTkLabel(
                                        container, 
                                        text="Extraction Failed!", 
                                        font=("Arial", 16, "bold"),
                                        text_color="#dc3545"
                                    )
                                    lbl_fail.pack(anchor="w", pady=(0, 15))

                                    lbl_desc = ctk.CTkLabel(
                                        container, 
                                        text=f"An error occurred while extracting scrcpy update:\n\n{result_status}", 
                                        font=("Arial", 12),
                                        justify="left",
                                        wrap=400
                                    )
                                    lbl_desc.pack(anchor="w", pady=(0, 20))

                                    btn_ok = ctk.CTkButton(
                                        container,
                                        text="Close",
                                        width=100,
                                        fg_color=("#eaeaea", "#2b2b2b"),
                                        border_width=1,
                                        text_color=("#111318", "#f2f2f2"),
                                        command=dialog.destroy
                                    )
                                    btn_ok.pack(side="right")

                            dialog.after(0, show_extract_result)

                        # Extract in background thread
                        def run_extraction():
                            try:
                                import zipfile
                                import shutil
                                from config.config import Config
                                
                                scrcpy_dir = os.path.join(Config.BIN_DIR, "scrcpy")
                                temp_extract = os.path.join(Config.CACHE_DIR, "scrcpy_update_extract")
                                
                                if os.path.exists(temp_extract):
                                    shutil.rmtree(temp_extract)
                                os.makedirs(temp_extract, exist_ok=True)
                                
                                with zipfile.ZipFile(dest_path, 'r') as zip_ref:
                                    zip_ref.extractall(temp_extract)
                                    
                                if os.path.exists(scrcpy_dir):
                                    shutil.rmtree(scrcpy_dir)
                                os.makedirs(scrcpy_dir, exist_ok=True)
                                
                                # Move files
                                items = os.listdir(temp_extract)
                                if len(items) == 1 and os.path.isdir(os.path.join(temp_extract, items[0])):
                                    inner_dir = os.path.join(temp_extract, items[0])
                                    for x_item in os.listdir(inner_dir):
                                        shutil.move(os.path.join(inner_dir, x_item), os.path.join(scrcpy_dir, x_item))
                                else:
                                    for x_item in items:
                                        shutil.move(os.path.join(temp_extract, x_item), os.path.join(scrcpy_dir, x_item))
                                        
                                shutil.rmtree(temp_extract, ignore_errors=True)
                                try:
                                    os.remove(dest_path)
                                except Exception:
                                    pass
                                on_extract_complete("Success")
                            except Exception as e:
                                on_extract_complete(str(e))

                        threading.Thread(target=run_extraction, daemon=True).start()

                    elif status == "Cancelled":
                        dialog.destroy()
                    else:
                        for child in container.winfo_children():
                            child.destroy()
                        lbl_fail = ctk.CTkLabel(
                            container, 
                            text="Download Failed!", 
                            font=("Arial", 16, "bold"),
                            text_color="#dc3545"
                        )
                        lbl_fail.pack(anchor="w", pady=(0, 15))
                        lbl_desc = ctk.CTkLabel(
                            container, 
                            text=f"Failed to download scrcpy update:\n\n{status}", 
                            font=("Arial", 12),
                            justify="left",
                            wrap=400
                        )
                        lbl_desc.pack(anchor="w", pady=(0, 20))
                        btn_ok = ctk.CTkButton(
                            container,
                            text="Close",
                            width=100,
                            fg_color=("#eaeaea", "#2b2b2b"),
                            border_width=1,
                            text_color=("#111318", "#f2f2f2"),
                            command=dialog.destroy
                        )
                        btn_ok.pack(side="right")

                dialog.after(0, update_ui)

            def on_window_close():
                downloader.cancel()
                dialog.destroy()

            dialog.protocol("WM_DELETE_WINDOW", on_window_close)
            downloader.start(progress_cb, completion_cb)

        btn_later = ctk.CTkButton(
            btn_frame,
            text="Later",
            width=80,
            fg_color="transparent",
            hover_color=("#e0e0e0", "#2a2a2a"),
            border_width=1,
            text_color=("#111318", "#f2f2f2"),
            command=on_later
        )
        btn_later.pack(side="right")

        btn_update = ctk.CTkButton(
            btn_frame,
            text="Update",
            width=100,
            fg_color="#0d6efd",
            hover_color="#0b5ed7",
            text_color="#ffffff",
            font=("Arial", 12, "bold"),
            command=on_update
        )
        btn_update.pack(side="right", padx=(0, 10))

    def _rotate_to_label(self, value):
        value_map = {1: 90, 2: 180, 3: 270, "1": 90, "2": 180, "3": 270}
        degrees = value_map.get(value, value)
        try:
            degrees = int(degrees)
        except (TypeError, ValueError):
            degrees = 0
        if degrees not in (0, 90, 180, 270):
            degrees = 0
        return f"{degrees} deg"

    def _rotate_from_label(self, value):
        try:
            return int(str(value).split()[0])
        except (TypeError, ValueError, IndexError):
            return 0

    def _is_error_log(self, message):
        lowered = message.lower()
        return "[error]" in lowered or "error:" in lowered or "gagal" in lowered or "failed" in lowered


if __name__ == "__main__":
    app = CameraStudioUI()
    app.apply_theme("Dark")
    app.append_log("Application initialized successfully.")
    app.mainloop()

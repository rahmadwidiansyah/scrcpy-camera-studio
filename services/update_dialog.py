import os
import customtkinter as ctk

class UpdateDialog(ctk.CTkToplevel):
    def __init__(self, parent, current_version, latest_version, release_notes, callbacks):
        """Initializes the modern update dialog window."""
        super().__init__(parent)
        self.title("Software Update")
        self.geometry("500x480")
        self.resizable(False, False)

        if hasattr(parent, '_set_window_icon'):
            parent._set_window_icon(self)

        self.current_version = current_version
        self.latest_version = latest_version
        self.release_notes = release_notes
        
        # Callbacks dict: on_update, on_pause, on_resume, on_cancel, on_install, on_close
        self.callbacks = callbacks

        # Make it modal/transient
        self.transient(parent)
        self.grab_set()
        self.focus_set()

        # Center window relative to parent
        self._center_window()

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=24, pady=24)

        self.show_release_details()

    def _center_window(self):
        self.update_idletasks()
        parent = self.master
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        x = parent_x + (parent_w - 500) // 2
        y = parent_y + (parent_h - 480) // 2
        self.geometry(f"500x480+{x}+{y}")

    def _clear_container(self):
        for child in self.container.winfo_children():
            child.destroy()

    def show_release_details(self):
        """State 1: Shows version details and release notes with Action buttons."""
        self._clear_container()

        lbl_title = ctk.CTkLabel(
            self.container, 
            text="Update Available!", 
            font=("Arial", 20, "bold")
        )
        lbl_title.pack(anchor="w", pady=(0, 15))

        # Version Info Box
        info_frame = ctk.CTkFrame(self.container, fg_color=("#eaeaea", "#22252a"), corner_radius=8)
        info_frame.pack(fill="x", pady=(0, 16), ipady=8)

        lbl_curr_version = ctk.CTkLabel(
            info_frame, 
            text=f"Current Version:  v{self.current_version}", 
            font=("Arial", 12)
        )
        lbl_curr_version.pack(anchor="w", padx=16, pady=(4, 2))

        lbl_latest_version = ctk.CTkLabel(
            info_frame, 
            text=f"Latest Version:     v{self.latest_version}", 
            font=("Arial", 12, "bold"),
            text_color="#2ECC71"
        )
        lbl_latest_version.pack(anchor="w", padx=16, pady=(2, 4))

        # Release Notes Label
        lbl_notes = ctk.CTkLabel(
            self.container, 
            text="Release Notes:", 
            font=("Arial", 12, "bold")
        )
        lbl_notes.pack(anchor="w", pady=(0, 6))

        # Release Notes Textbox
        txt_notes = ctk.CTkTextbox(
            self.container, 
            height=180, 
            wrap="word", 
            fg_color=("#111318", "#111318"),
            text_color="#f2f2f2"
        )
        txt_notes.pack(fill="both", expand=True, pady=(0, 20))
        
        notes_content = self.release_notes.strip() if self.release_notes else "No release notes available."
        txt_notes.insert("1.0", notes_content)
        txt_notes.configure(state="disabled")

        # Buttons Row
        btn_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        btn_frame.pack(fill="x", side="bottom")

        btn_close = ctk.CTkButton(
            btn_frame,
            text="Close",
            width=80,
            fg_color="transparent",
            hover_color=("#e0e0e0", "#2a2a2a"),
            border_width=1,
            text_color=("#111318", "#f2f2f2"),
            command=self.callbacks.get("on_close")
        )
        btn_close.pack(side="right")

        btn_later = ctk.CTkButton(
            btn_frame,
            text="Later",
            width=80,
            fg_color="transparent",
            hover_color=("#e0e0e0", "#2a2a2a"),
            border_width=1,
            text_color=("#111318", "#f2f2f2"),
            command=self.callbacks.get("on_close")
        )
        btn_later.pack(side="right", padx=(0, 12))

        btn_update = ctk.CTkButton(
            btn_frame,
            text="Update",
            width=100,
            fg_color="#0d6efd",
            hover_color="#0b5ed7",
            text_color="#ffffff",
            font=("Arial", 12, "bold"),
            command=self.callbacks.get("on_update")
        )
        btn_update.pack(side="right", padx=(0, 12))

    def show_download_progress(self):
        """State 2: Shows real-time progress bar, speed, ETA, and Pause/Cancel buttons."""
        self._clear_container()

        self.lbl_progress_title = ctk.CTkLabel(
            self.container, 
            text="Downloading Update...", 
            font=("Arial", 20, "bold")
        )
        self.lbl_progress_title.pack(anchor="w", pady=(0, 20))

        self.progress_bar = ctk.CTkProgressBar(self.container)
        self.progress_bar.pack(fill="x", pady=(0, 12))
        self.progress_bar.set(0.0)

        self.lbl_status = ctk.CTkLabel(
            self.container, 
            text="Connecting to server...", 
            font=("Arial", 12),
            anchor="w"
        )
        self.lbl_status.pack(anchor="w", pady=(0, 4))

        self.lbl_speed_eta = ctk.CTkLabel(
            self.container, 
            text="", 
            font=("Arial", 11),
            text_color=("#555555", "#aaaaaa"),
            anchor="w"
        )
        self.lbl_speed_eta.pack(anchor="w", pady=(0, 30))

        btn_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        btn_frame.pack(fill="x", side="bottom")

        btn_cancel = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            fg_color="transparent",
            hover_color=("#E74C3C", "#E74C3C"),
            border_width=1,
            text_color=("#111318", "#f2f2f2"),
            command=self.callbacks.get("on_cancel")
        )
        btn_cancel.pack(side="right")

        self.is_paused_state = False

        def toggle_pause():
            if self.is_paused_state:
                self.callbacks.get("on_resume")()
                self.is_paused_state = False
                self.btn_pause.configure(text="Pause", fg_color="transparent", border_width=1, hover_color=("#e0e0e0", "#2a2a2a"))
                self.lbl_progress_title.configure(text="Downloading Update...")
            else:
                self.callbacks.get("on_pause")()
                self.is_paused_state = True
                self.btn_pause.configure(text="Resume", fg_color="#198754", border_width=0, hover_color="#157347")
                self.lbl_progress_title.configure(text="Downloading Paused")
                self.lbl_status.configure(text="Download paused by user.")
                self.lbl_speed_eta.configure(text="")

        self.btn_pause = ctk.CTkButton(
            btn_frame,
            text="Pause",
            width=100,
            fg_color="transparent",
            hover_color=("#e0e0e0", "#2a2a2a"),
            border_width=1,
            text_color=("#111318", "#f2f2f2"),
            command=toggle_pause
        )
        self.btn_pause.pack(side="right", padx=(0, 12))

    def update_progress_ui(self, percentage, downloaded_mb, total_mb, speed_mb, eta):
        """Updates the real-time values of the download progress."""
        if hasattr(self, 'progress_bar') and not self.is_paused_state:
            self.progress_bar.set(percentage / 100.0)
            
            status_text = f"Downloaded {downloaded_mb:.2f} MB of {total_mb:.2f} MB ({int(percentage)}%)" if total_mb > 0 else f"Downloaded {downloaded_mb:.2f} MB"
            self.lbl_status.configure(text=status_text)
            
            speed_text = f"{speed_mb:.2f} MB/s"
            if eta > 0:
                eta_text = f"{int(eta)}s remaining" if eta < 60 else f"{int(eta // 60)}m {int(eta % 60)}s remaining"
                self.lbl_speed_eta.configure(text=f"Speed: {speed_text}  •  {eta_text}")
            else:
                self.lbl_speed_eta.configure(text=f"Speed: {speed_text}")

    def show_install_ready(self):
        """State 3: Shows verification complete and displays 'Restart & Install' button."""
        self._clear_container()

        lbl_title = ctk.CTkLabel(
            self.container, 
            text="Download Complete!", 
            font=("Arial", 20, "bold"),
            text_color="#2ECC71"
        )
        lbl_title.pack(anchor="w", pady=(0, 15))

        lbl_desc = ctk.CTkLabel(
            self.container, 
            text="The update has been successfully downloaded and verified.\n\nClick 'Restart & Install' to perform the update. The application will close automatically.", 
            font=("Arial", 12),
            justify="left",
            wrap=450
        )
        lbl_desc.pack(anchor="w", pady=(0, 30))

        btn_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        btn_frame.pack(fill="x", side="bottom")

        btn_later = ctk.CTkButton(
            btn_frame,
            text="Later",
            width=100,
            fg_color="transparent",
            hover_color=("#e0e0e0", "#2a2a2a"),
            border_width=1,
            text_color=("#111318", "#f2f2f2"),
            command=self.callbacks.get("on_close")
        )
        btn_later.pack(side="right")

        btn_install = ctk.CTkButton(
            btn_frame,
            text="Restart & Install",
            width=140,
            fg_color="#198754",
            hover_color="#157347",
            text_color="#ffffff",
            font=("Arial", 12, "bold"),
            command=self.callbacks.get("on_install")
        )
        btn_install.pack(side="right", padx=(0, 12))

    def show_error(self, message):
        """State 4: Shows error details with a Close button."""
        self._clear_container()

        lbl_title = ctk.CTkLabel(
            self.container, 
            text="Download Failed!", 
            font=("Arial", 20, "bold"),
            text_color="#E74C3C"
        )
        lbl_title.pack(anchor="w", pady=(0, 15))

        lbl_desc = ctk.CTkLabel(
            self.container, 
            text=f"An error occurred while downloading the update:\n\n{message}", 
            font=("Arial", 12),
            justify="left",
            wrap=450
        )
        lbl_desc.pack(anchor="w", pady=(0, 30))

        btn_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        btn_frame.pack(fill="x", side="bottom")

        btn_close = ctk.CTkButton(
            btn_frame,
            text="Close",
            width=100,
            fg_color=("#eaeaea", "#2b2b2b"),
            border_width=1,
            text_color=("#111318", "#f2f2f2"),
            command=self.callbacks.get("on_close")
        )
        btn_close.pack(side="right")

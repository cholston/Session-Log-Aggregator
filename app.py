import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import os
import shutil
import threading
from datetime import datetime
from mergesessionlogs import merge_logs
from transcription import transcribe_whisper
from transcription_gemini import transcribe_gemini
from dotenv import load_dotenv, set_key
import traceback
from foundry_scraper import download_foundry_chat_log

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")
env_path = ".env"

class LogAggregatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Session Log Aggregator")
        self.geometry("600x550")

        # Configure grid layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(7, weight=1)

        # Variables for file paths
        self.fvtt_path_var = tk.StringVar()
        self.transcript_path_var = tk.StringVar()
        self.api_key_var = tk.StringVar()
        self.transcription_mode = tk.StringVar(value="whisper")
        
        load_dotenv(env_path)
        if os.getenv("GEMINI_API_KEY"):
            self.api_key_var.set(os.getenv("GEMINI_API_KEY"))
            
        self.last_output_dir = os.getenv("LAST_OUTPUT_DIR", "")

        # UI Elements
        # FoundryVTT File Row
        self.fvtt_label = ctk.CTkLabel(self, text="FoundryVTT Chat Log:", anchor="w")
        self.fvtt_label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")

        self.fvtt_entry = ctk.CTkEntry(self, textvariable=self.fvtt_path_var, state="readonly")
        self.fvtt_entry.grid(row=0, column=1, padx=(0, 10), pady=(20, 10), sticky="ew")

        # Create a frame for the buttons so they can be side-by-side
        self.fvtt_button_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.fvtt_button_frame.grid(row=0, column=2, padx=(0, 20), pady=(20, 10), sticky="e")

        self.fvtt_button = ctk.CTkButton(self.fvtt_button_frame, text="Browse", width=80, command=self.browse_fvtt)
        self.fvtt_button.pack(side="left", padx=(0, 5))
        
        self.fvtt_download_btn = ctk.CTkButton(self.fvtt_button_frame, text="Download", width=80, fg_color="#cf5f00", hover_color="#8f4302", command=self.download_fvtt)
        self.fvtt_download_btn.pack(side="left")

        # Transcript / Audio File Row
        self.transcript_label = ctk.CTkLabel(self, text="Audio/Transcript File:", anchor="w")
        self.transcript_label.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        self.transcript_entry = ctk.CTkEntry(self, textvariable=self.transcript_path_var, state="readonly")
        self.transcript_entry.grid(row=1, column=1, padx=(0, 10), pady=10, sticky="ew")

        self.transcript_button = ctk.CTkButton(self, text="Browse", command=self.browse_transcript)
        self.transcript_button.grid(row=1, column=2, padx=(0, 20), pady=10)
        
        # API Key Row
        self.api_key_label = ctk.CTkLabel(self, text="Gemini API Key\n(Optional - not used for audio):", anchor="w")
        self.api_key_label.grid(row=2, column=0, padx=20, pady=10, sticky="w")
        
        self.api_key_entry = ctk.CTkEntry(self, textvariable=self.api_key_var, show="*")
        self.api_key_entry.grid(row=2, column=1, padx=(0, 20), pady=10, sticky="ew", columnspan=2)

        # Start Time Row
        self.time_label = ctk.CTkLabel(self, text="Recording Start Time\n(Match Foundry Timezone)\nFormat: YYYY-MM-DD HH:MM:SS", anchor="w")
        self.time_label.grid(row=3, column=0, padx=20, pady=10, sticky="w")

        self.time_entry = ctk.CTkEntry(self, placeholder_text="e.g., 2026-02-07 16:28:54")
        self.time_entry.insert(0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.time_entry.grid(row=3, column=1, padx=(0, 20), pady=10, sticky="ew", columnspan=2)

        # Transcription Mode Row
        self.mode_label = ctk.CTkLabel(self, text="Transcription Method:", anchor="w")
        self.mode_label.grid(row=4, column=0, padx=20, pady=10, sticky="w")

        self.mode_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.mode_frame.grid(row=4, column=1, padx=(0, 20), pady=10, sticky="ew", columnspan=2)

        self.whisper_radio = ctk.CTkRadioButton(self.mode_frame, text="Whisper (Local)", variable=self.transcription_mode, value="whisper")
        self.whisper_radio.pack(side="left", padx=(0, 20))

        self.gemini_radio = ctk.CTkRadioButton(self.mode_frame, text="Gemini (Cloud)", variable=self.transcription_mode, value="gemini")
        self.gemini_radio.pack(side="left")

        # Merge Button
        self.merge_button = ctk.CTkButton(self, text="Merge Logs", command=self.process_merge_thread, height=40, font=ctk.CTkFont(size=14, weight="bold"))
        self.merge_button.grid(row=5, column=0, columnspan=3, padx=20, pady=30, sticky="ew")

        # Status Label
        self.status_label = ctk.CTkLabel(self, text="Ready", text_color="gray")
        self.status_label.grid(row=6, column=0, columnspan=3, padx=20, pady=10)

    def browse_fvtt(self):
        filename = filedialog.askopenfilename(
            title="Select FoundryVTT Chat Log",
            filetypes=(("Text Files", "*.txt"), ("All Files", "*.*"))
        )
        if filename:
            self.fvtt_path_var.set(filename)

    def browse_transcript(self):
        filename = filedialog.askopenfilename(
            title="Select Audio or Transcript",
            filetypes=(("Text/Audio Files", "*.txt *.mp3 *.wav *.ogg *.m4a *.aac"), ("All Files", "*.*"))
        )
        if filename:
            self.transcript_path_var.set(filename)

    def download_fvtt(self):
        # Open configuration dialog if parameters are missing
        url = os.getenv("FOUNDRY_URL")
        username = os.getenv("FOUNDRY_USERNAME")
        password = os.getenv("FOUNDRY_PASSWORD")
        
        if not url or not username:
            self.open_foundry_config()
            return
            
        # Start download thread to keep UI responsive
        self.status_label.configure(text="Launching headless browser...", text_color="yellow")
        self.fvtt_download_btn.configure(state="disabled")
        
        thread = threading.Thread(target=self.process_download, args=(url, username, password), daemon=True)
        thread.start()

    def process_download(self, url, username, password):
        try:
            self.after(0, lambda: self.status_label.configure(text=f"Connecting to {url}...", text_color="yellow"))
            
            save_path = download_foundry_chat_log(url, username, password)
            
            if save_path:
                self.after(0, lambda: self.fvtt_path_var.set(save_path))
                self.after(0, lambda: self.status_label.configure(text="Downloaded chat log successfully!", text_color="green"))
            else:
                self.after(0, lambda: self.status_label.configure(text="Download failed. Check console for errors.", text_color="red"))
                self.after(0, lambda: messagebox.showerror("Download Failed", "Could not download chat log. Ensure server is running and credentials are correct."))
                
        except Exception as e:
            self.after(0, lambda: self.status_label.configure(text="Error occurred during download", text_color="red"))
            self.after(0, lambda: messagebox.showerror("Error", f"Automation error:\n{str(e)}"))
        finally:
            self.after(0, lambda: self.fvtt_download_btn.configure(state="normal"))

    def open_foundry_config(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("FoundryVTT Scraper Configuration")
        dialog.geometry("400x300")
        dialog.transient(self)  # Keep on top of main window
        dialog.grab_set()       # Make modal
        
        ctk.CTkLabel(dialog, text="Server URL (e.g. https://my-game.forge-vtt.com):").pack(pady=(20, 5), padx=20, anchor="w")
        url_entry = ctk.CTkEntry(dialog, width=360)
        url_entry.pack(pady=5, padx=20)
        url_entry.insert(0, os.getenv("FOUNDRY_URL", ""))
        
        ctk.CTkLabel(dialog, text="Foundry Username:").pack(pady=5, padx=20, anchor="w")
        user_entry = ctk.CTkEntry(dialog, width=360)
        user_entry.pack(pady=5, padx=20)
        user_entry.insert(0, os.getenv("FOUNDRY_USERNAME", ""))
        
        ctk.CTkLabel(dialog, text="Foundry Password (Optional):").pack(pady=5, padx=20, anchor="w")
        pass_entry = ctk.CTkEntry(dialog, width=360, show="*")
        pass_entry.pack(pady=5, padx=20)
        pass_entry.insert(0, os.getenv("FOUNDRY_PASSWORD", ""))
        
        def save_config():
            url = url_entry.get().strip()
            user = user_entry.get().strip()
            pwd = pass_entry.get().strip()
            
            if not url or not user:
                messagebox.showwarning("Warning", "URL and Username are required.", parent=dialog)
                return
                
            set_key(env_path, "FOUNDRY_URL", url)
            set_key(env_path, "FOUNDRY_USERNAME", user)
            set_key(env_path, "FOUNDRY_PASSWORD", pwd)
            
            # Update local environment variables so download logic works immediately
            os.environ["FOUNDRY_URL"] = url
            os.environ["FOUNDRY_USERNAME"] = user
            os.environ["FOUNDRY_PASSWORD"] = pwd
            
            messagebox.showinfo("Success", "Configuration saved! Click Download again.", parent=dialog)
            dialog.destroy()
            
        save_btn = ctk.CTkButton(dialog, text="Save Settings", command=save_config)
        save_btn.pack(pady=20)

    def process_merge_thread(self):
        # Disable button while working
        self.merge_button.configure(state="disabled")
        
        thread = threading.Thread(target=self.process_merge, daemon=True)
        thread.start()

    def process_merge(self):
        try:
            fvtt_path = self.fvtt_path_var.get()
            transcript_path = self.transcript_path_var.get()
            start_time_str = self.time_entry.get().strip()
            api_key_val = self.api_key_var.get().strip()

            if not fvtt_path:
                self.after(0, lambda: messagebox.showwarning("Warning", "Please select a FoundryVTT chat log file."))
                return
            if not transcript_path:
                self.after(0, lambda: messagebox.showwarning("Warning", "Please select an Audio or Transcript file."))
                return
            if not start_time_str:
                self.after(0, lambda: messagebox.showwarning("Warning", "Please enter the recording start time."))
                return

            try:
                start_time = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                self.after(0, lambda: messagebox.showerror("Error", "Invalid time format. Please use YYYY-MM-DD HH:MM:SS"))
                return
                
            is_audio = not transcript_path.lower().endswith('.txt')
            if is_audio and api_key_val:
                set_key(env_path, "GEMINI_API_KEY", api_key_val)

            initial_dir = self.last_output_dir if self.last_output_dir else os.path.expanduser("~")
            current_date = datetime.now().strftime("%Y-%m-%d")
            output_path = filedialog.asksaveasfilename(
                title="Save Merged Log As",
                defaultextension=".md",
                initialdir=initial_dir,
                filetypes=(("Markdown Files", "*.md"), ("Text Files", "*.txt")),
                initialfile=f"{current_date}-Transcript.md"
            )

            if not output_path:
                return  # User cancelled save dialog
                
            self.last_output_dir = os.path.dirname(output_path)
            set_key(env_path, "LAST_OUTPUT_DIR", self.last_output_dir)

            self.after(0, lambda: self.status_label.configure(text="Processing...", text_color="yellow"))

            if is_audio:
                mode = self.transcription_mode.get()
                if mode == "whisper":
                    self.after(0, lambda: self.status_label.configure(text="Transcribing audio with Whisper...\n(This may take a few minutes, please wait)", text_color="yellow"))
                    transcript_path = transcribe_whisper(transcript_path)
                else:
                    if not api_key_val:
                        self.after(0, lambda: messagebox.showwarning("Warning", "Gemini API Key is required for Gemini transcription."))
                        return
                    self.after(0, lambda: self.status_label.configure(text="Transcribing audio with Gemini...\n(Uploading and generating...)", text_color="yellow"))
                    transcript_path = transcribe_gemini(transcript_path, api_key_val)

            self.after(0, lambda: self.status_label.configure(text="Merging logs...", text_color="yellow"))
                
            merge_logs(fvtt_path, transcript_path, output_path, start_time)
            
            # Archive the temp transcript if it existed
            if is_audio and os.path.exists(transcript_path):
                try:
                    archive_dir = os.path.join(os.path.dirname(transcript_path), "archived")
                    os.makedirs(archive_dir, exist_ok=True)
                    shutil.move(transcript_path, os.path.join(archive_dir, os.path.basename(transcript_path)))
                except Exception as e:
                    print(f"Failed to archive transcript: {e}")

            self.after(0, lambda: self.status_label.configure(text=f"Successfully generated {os.path.basename(output_path)}!", text_color="green"))
            self.after(0, lambda: messagebox.showinfo("Success", "Log merge completed successfully."))
            
        except Exception as e:
            error_details = traceback.format_exc()
            print(error_details)
            self.after(0, lambda: self.status_label.configure(text="Error occurred", text_color="red"))
            self.after(0, lambda: messagebox.showerror("Execution Error", f"An error occurred:\n\n{str(e)}\n\nSee below for details:\n{error_details}"))
        finally:
            self.after(0, lambda: self.merge_button.configure(state="normal"))

if __name__ == "__main__":
    app = LogAggregatorApp()
    app.mainloop()

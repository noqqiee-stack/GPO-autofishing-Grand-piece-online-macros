import tkinter as tk
from tkinter import ttk
import threading
import keyboard
from pynput import keyboard as pynput_keyboard
from pynput import mouse as pynput_mouse
from tkinter import messagebox
import sys
import ctypes
import mss
import numpy as np
import win32api
import win32com
import win32con

class HotkeyGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("ds - noq1e and akumaeeee")

        # Make GUI always on top
        self.root.attributes('-topmost', True)

        # Make app DPI aware on Windows
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass

        # Configure root grid weights for proper resizing
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # State variables
        self.main_loop_active = False
        self.overlay_active = False
        self.main_loop_thread = None
        self.recording_hotkey = None
        self.overlay_window = None
        self.real_area = None  # Will store the calculated real scanning area
        self.is_clicking = False  # Track if left click is currently held

        # PD controller parameters
        self.kp = 0.1  # Proportional gain
        self.kd = 0.5  # Derivative gain
        self.previous_error = 0

        # Timing parameters
        self.scan_timeout = 15.0  # Seconds before re-casting
        self.wait_after_loss = 1.0  # Seconds to wait after losing detection

        # Get DPI scaling factor
        self.dpi_scale = self.get_dpi_scale()

        # Overlay area storage (base dimensions at 100% DPI)
        base_width = 172
        base_height = 495

        self.overlay_area = {
            'x': int(100 * self.dpi_scale),
            'y': int(100 * self.dpi_scale),
            'width': int(base_width * self.dpi_scale),
            'height': int(base_height * self.dpi_scale)
        }

        # Default hotkeys
        self.hotkeys = {
            'toggle_loop': 'f1',
            'toggle_overlay': 'f2',
            'exit': 'f3'
        }

        # Purchase counter for auto-purchase sequencing
        self.purchase_counter = 0
        # Auto-purchase timing delays (seconds)
        self.purchase_delay_after_key = 2.0
        self.purchase_click_delay = 1.0
        self.purchase_after_type_delay = 1.0

        # Initialize mss screen capture
        self.sct = None

        # Create GUI
        self.create_widgets()

        # Register hotkeys
        self.register_hotkeys()

        # Update window to calculate proper size, then set minimum size
        self.root.update_idletasks()
        self.root.minsize(self.root.winfo_width(), self.root.winfo_height())

    def get_dpi_scale(self):
        """Get the DPI scaling factor for the current display"""
        try:
            # Get the DPI scaling from tkinter
            dpi = self.root.winfo_fpixels('1i')
            scale = dpi / 96.0  # 96 DPI is 100% scaling
            return scale
        except:
            return 1.0  # Default to 100% if unable to detect

    def create_widgets(self):
        # Set background color for root window
        self.root.configure(bg='#191919')

        # Create canvas and scrollbar
        canvas = tk.Canvas(self.root, bg='#191919', highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.root, orient='vertical', command=canvas.yview)
        
        # Main frame inside canvas
        main_frame = ttk.Frame(canvas, padding="20")

        # Configure canvas scrolling
        canvas.configure(yscrollcommand=scrollbar.set)

        # Pack scrollbar and canvas
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Create window in canvas
        canvas_frame = canvas.create_window((0, 0), window=main_frame, anchor="nw")

        # Configure main_frame grid weights
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=0)
        main_frame.columnconfigure(2, weight=0)

        # Update scroll region when frame changes size
        def configure_scroll_region(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Also update canvas window width to match canvas width
            canvas_width = canvas.winfo_width()
            canvas.itemconfig(canvas_frame, width=canvas_width)

        main_frame.bind("<Configure>", configure_scroll_region)
        canvas.bind("<Configure>", configure_scroll_region)

        # Bind mousewheel scrolling
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        canvas.bind_all("<MouseWheel>", on_mousewheel)

        # Title
        title = ttk.Label(main_frame, text="ds - noq1e and akumaeeee", font=('Arial', 16, 'bold'))
        title.grid(row=0, column=0, columnspan=3, pady=(0, 10))

        # Status Indicators
        self.loop_status = ttk.Label(main_frame, text="Main Loop: OFF", foreground="#55aaff")
        self.loop_status.grid(row=1, column=0, columnspan=3, pady=5)
        
        self.overlay_status = ttk.Label(main_frame, text="Overlay: OFF", foreground="#55aaff")
        self.overlay_status.grid(row=2, column=0, columnspan=3, pady=5)

        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=3, column=0, columnspan=3, sticky='ew', pady=20)

        # Auto Purchase Settings (inserted above PD Controller)
        ttk.Label(main_frame, text="Auto Purchase Settings:", font=('Arial', 12, 'bold')).grid(row=4, column=0, columnspan=3, pady=(0, 10))

        # Active (Enable/Disable)
        ttk.Label(main_frame, text="Active:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.auto_purchase_var = tk.BooleanVar(value=False)
        auto_check = ttk.Checkbutton(main_frame, variable=self.auto_purchase_var, text="Enabled")
        auto_check.grid(row=5, column=1, columnspan=2, pady=5, sticky=tk.W)

        # Amount
        ttk.Label(main_frame, text="Amount:").grid(row=6, column=0, sticky=tk.W, pady=5)
        self.amount_var = tk.IntVar(value=10)
        amount_spinbox = ttk.Spinbox(main_frame, from_=0, to=1000000, increment=1, textvariable=self.amount_var, width=10)
        amount_spinbox.grid(row=6, column=1, columnspan=2, pady=5, sticky=tk.W)
        self.amount_var.trace_add('write', lambda *args: setattr(self, 'auto_purchase_amount', self.amount_var.get()))
        self.auto_purchase_amount = self.amount_var.get()

        # Loops per purchase
        ttk.Label(main_frame, text="Loops per Purchase:").grid(row=7, column=0, sticky=tk.W, pady=5)
        self.loops_var = tk.IntVar(value=10)
        loops_spinbox = ttk.Spinbox(main_frame, from_=1, to=1000000, increment=1, textvariable=self.loops_var, width=10)
        loops_spinbox.grid(row=7, column=1, columnspan=2, pady=5, sticky=tk.W)
        self.loops_var.trace_add('write', lambda *args: setattr(self, 'loops_per_purchase', self.loops_var.get()))
        self.loops_per_purchase = self.loops_var.get()

        # Point capture buttons
        ttk.Label(main_frame, text="Point 1:").grid(row=8, column=0, sticky=tk.W, pady=5)
        self.point_buttons = {}
        self.point_coords = {1: None, 2: None, 3: None, 4: None}
        self.point_buttons[1] = ttk.Button(main_frame, text='Point 1', command=lambda: self.capture_mouse_click(1))
        self.point_buttons[1].grid(row=8, column=1, columnspan=2, pady=5, sticky=tk.W)

        ttk.Label(main_frame, text='Point 2:').grid(row=9, column=0, sticky=tk.W, pady=5)
        self.point_buttons[2] = ttk.Button(main_frame, text='Point 2', command=lambda: self.capture_mouse_click(2))
        self.point_buttons[2].grid(row=9, column=1, columnspan=2, pady=5, sticky=tk.W)

        ttk.Label(main_frame, text='Point 3:').grid(row=10, column=0, sticky=tk.W, pady=5)
        self.point_buttons[3] = ttk.Button(main_frame, text='Point 3', command=lambda: self.capture_mouse_click(3))
        self.point_buttons[3].grid(row=10, column=1, columnspan=2, pady=5, sticky=tk.W)

        ttk.Label(main_frame, text='Point 4:').grid(row=11, column=0, sticky=tk.W, pady=5)
        self.point_buttons[4] = ttk.Button(main_frame, text='Point 4', command=lambda: self.capture_mouse_click(4))
        self.point_buttons[4].grid(row=11, column=1, columnspan=2, pady=5, sticky=tk.W)

        # Separator (after Auto Purchase)
        ttk.Separator(main_frame, orient='horizontal').grid(row=12, column=0, columnspan=3, sticky='ew', pady=20)

        # PD Controller Settings (shifted down)
        ttk.Label(main_frame, text="PD Controller:", font=('Arial', 12, 'bold')).grid(row=13, column=0, columnspan=3, pady=(0, 10))

        # Kp
        ttk.Label(main_frame, text="Kp (Proportional):").grid(row=14, column=0, sticky=tk.W, pady=5)
        self.kp_var = tk.DoubleVar(value=self.kp)
        kp_spinbox = ttk.Spinbox(main_frame, from_=0.0, to=2.0, increment=0.1, textvariable=self.kp_var, width=10)
        kp_spinbox.grid(row=14, column=1, columnspan=2, pady=5, sticky=tk.W)
        self.kp_var.trace_add('write', lambda *args: setattr(self, 'kp', self.kp_var.get()))

        # Kd
        ttk.Label(main_frame, text="Kd (Derivative):").grid(row=15, column=0, sticky=tk.W, pady=5)
        self.kd_var = tk.DoubleVar(value=self.kd)
        kd_spinbox = ttk.Spinbox(main_frame, from_=0.0, to=1.0, increment=0.01, textvariable=self.kd_var, width=10)
        kd_spinbox.grid(row=15, column=1, columnspan=2, pady=5, sticky=tk.W)
        self.kd_var.trace_add('write', lambda *args: setattr(self, 'kd', self.kd_var.get()))

        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=16, column=0, columnspan=3, sticky='ew', pady=20)

        # Timing Settings (shifted down)
        ttk.Label(main_frame, text="Timing Settings:", font=('Arial', 12, 'bold')).grid(row=17, column=0, columnspan=3, pady=(0, 10))

        # Scan Timeout
        ttk.Label(main_frame, text="Scan Timeout (s):").grid(row=18, column=0, sticky=tk.W, pady=5)
        self.timeout_var = tk.DoubleVar(value=self.scan_timeout)
        timeout_spinbox = ttk.Spinbox(main_frame, from_=1.0, to=60.0, increment=1.0, textvariable=self.timeout_var, width=10)
        timeout_spinbox.grid(row=18, column=1, columnspan=2, pady=5, sticky=tk.W)
        self.timeout_var.trace_add('write', lambda *args: setattr(self, 'scan_timeout', self.timeout_var.get()))

        # Wait After Loss
        ttk.Label(main_frame, text="Wait After Loss (s):").grid(row=19, column=0, sticky=tk.W, pady=5)
        self.wait_var = tk.DoubleVar(value=self.wait_after_loss)
        wait_spinbox = ttk.Spinbox(main_frame, from_=0.0, to=10.0, increment=0.1, textvariable=self.wait_var, width=10)
        wait_spinbox.grid(row=19, column=1, columnspan=2, pady=5, sticky=tk.W)
        self.wait_var.trace_add('write', lambda *args: setattr(self, 'wait_after_loss', self.wait_var.get()))

        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=20, column=0, columnspan=3, sticky='ew', pady=20)

        # Hotkey bindings (shifted down)
        ttk.Label(main_frame, text="Hotkey Bindings:", font=('Arial', 12, 'bold')).grid(row=21, column=0, columnspan=3, pady=(0, 10))

        # Toggle Loop
        ttk.Label(main_frame, text="Toggle Main Loop:").grid(row=22, column=0, sticky=tk.W, pady=5)
        self.loop_key_label = ttk.Label(main_frame, text=self.hotkeys['toggle_loop'].upper(),
                                      relief=tk.RIDGE, padding=5, width=10)
        self.loop_key_label.grid(row=22, column=1, pady=5)
        self.loop_rebind_btn = ttk.Button(main_frame, text="Rebind",
                                        command=lambda: self.start_rebind('toggle_loop'))
        self.loop_rebind_btn.grid(row=22, column=2, padx=5, pady=5)

        # Toggle Overlay
        ttk.Label(main_frame, text="Toggle Overlay:").grid(row=23, column=0, sticky=tk.W, pady=5)
        self.overlay_key_label = ttk.Label(main_frame, text=self.hotkeys['toggle_overlay'].upper(),
                                         relief=tk.RIDGE, padding=5, width=10)
        self.overlay_key_label.grid(row=23, column=1, pady=5)
        self.overlay_rebind_btn = ttk.Button(main_frame, text="Rebind",
                                           command=lambda: self.start_rebind('toggle_overlay'))
        self.overlay_rebind_btn.grid(row=23, column=2, padx=5, pady=5)

        # Exit
        ttk.Label(main_frame, text="Exit:").grid(row=24, column=0, sticky=tk.W, pady=5)
        self.exit_key_label = ttk.Label(main_frame, text=self.hotkeys['exit'].upper(),
                                      relief=tk.RIDGE, padding=5, width=10)
        self.exit_key_label.grid(row=24, column=1, pady=5)
        self.exit_rebind_btn = ttk.Button(main_frame, text="Rebind",
                                        command=lambda: self.start_rebind('exit'))
        self.exit_rebind_btn.grid(row=24, column=2, padx=5, pady=5)

        # Status message
        self.status_msg = ttk.Label(main_frame, text="", foreground="blue")
        self.status_msg.grid(row=25, column=0, columnspan=3, pady=(20, 0))

    def capture_mouse_click(self, idx):
        """Start a listener to capture the next mouse click and store its coordinates."""
        try:
            # Inform user
            if hasattr(self, 'status_msg'):
                self.status_msg.config(text=f'Click anywhere to set Point {idx}...', foreground="blue")

            def on_click(x, y, button, pressed):
                # Only act on press (not release)
                if pressed:
                    # Save coords
                    self.point_coords[idx] = (x, y)

                    # Update UI from main thread
                    try:
                        self.root.after(0, lambda: self.update_point_button(idx))
                        self.root.after(0, lambda: self.status_msg.config(text=f'Point {idx} set: ({x}, {y})', foreground="green"))
                    except Exception:
                        pass

                    return False  # stop listener

            listener = pynput_mouse.Listener(on_click=on_click)
            listener.start()
        except Exception as e:
            try:
                self.status_msg.config(text=f"Error capturing point: {e}", foreground="red")
            except Exception:
                pass

    def update_point_button(self, idx):
        coords = self.point_coords.get(idx)
        if coords and idx in self.point_buttons:
            self.point_buttons[idx].config(text=f"Point {idx}: {coords}")
        elif idx in self.point_buttons:
            self.point_buttons[idx].config(text=f"Point {idx}")

    def _click_at(self, coords):
        """Move cursor to coords and perform a left click."""
        try:
            x, y = int(coords[0]), int(coords[1])
            win32api.SetCursorPos((x, y))
            # anti-roblox: perform a tiny relative move so the client registers the cursor reposition
            try:
                win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, 1, 0, 0)
            except Exception:
                pass
            threading.Event().wait(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            threading.Event().wait(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        except Exception as e:
            print(f"Error clicking at {coords}: {e}")

    def perform_auto_purchase_sequence(self):
        """Perform the auto-purchase sequence using saved points and amount.

        Sequence (per user spec):
        - press 'e', wait
        - click point1, wait
        - click point2, wait
        - type amount, wait
        - click point1, wait
        - click point3, wait
        - click point2, wait
        """
        print("== AUTO-PURCHASE SEQUENCE START ==")
        pts = self.point_coords
        if not pts or not pts.get(1) or not pts.get(2) or not pts.get(3) or not pts.get(4):
            # Shouldn't happen if validated, but guard anyway
            print("Auto purchase aborted: points not fully set (need points 1-4).")
            return

        try:
            # Press 'e'
            print("Step 1: Pressing 'e'...")
            keyboard.press_and_release('e')
            threading.Event().wait(self.purchase_delay_after_key)

            # Click sequence
            print(f"Step 2: Clicking point 1 at {pts[1]}")
            self._click_at(pts[1])
            threading.Event().wait(self.purchase_click_delay)

            print(f"Step 3: Clicking point 2 at {pts[2]}")
            self._click_at(pts[2])
            threading.Event().wait(self.purchase_click_delay)

            # Type the amount
            amount = int(self.amount_var.get()) if hasattr(self, 'amount_var') else getattr(self, 'auto_purchase_amount', 10)
            print(f"Step 4: Typing amount: {amount}")
            keyboard.write(str(amount))
            threading.Event().wait(self.purchase_after_type_delay)

            # Continue clicks
            print(f"Step 5: Clicking point 1 at {pts[1]}")
            self._click_at(pts[1])
            threading.Event().wait(self.purchase_click_delay)

            print(f"Step 6: Clicking point 3 at {pts[3]}")
            self._click_at(pts[3])
            threading.Event().wait(self.purchase_click_delay)

            print(f"Step 7: Clicking point 2 at {pts[2]}")
            self._click_at(pts[2])
            threading.Event().wait(self.purchase_click_delay)

            # Move cursor to Point 4 after sequence if active and point 4 is set
            try:
                if getattr(self, 'auto_purchase_var', None) and self.auto_purchase_var.get():
                    p4 = pts.get(4)
                    if p4:
                        print(f"Step 8: Moving cursor to point 4 at {p4}")
                        # Move cursor to p4 but do not click. Use a tiny relative move so Roblox registers it.
                        win32api.SetCursorPos((int(p4[0]), int(p4[1])))
                        # anti-roblox: move by 1 pixel to force the client to register the cursor move
                        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, 1, 0, 0)
                        threading.Event().wait(self.purchase_click_delay)
            except Exception as ex:
                print(f"Error moving to point 4: {ex}")

            print(f"== AUTO-PURCHASE COMPLETE (amount={amount}) ==")
        except Exception as e:
            print(f"!!! ERROR during auto purchase sequence: {e} !!!")

    def start_rebind(self, action):
        """Start recording a new hotkey"""
        self.recording_hotkey = action
        self.status_msg.config(text=f"Press a key to rebind '{action}'...", foreground="blue")

        # Disable all rebind buttons
        self.loop_rebind_btn.config(state='disabled')
        self.overlay_rebind_btn.config(state='disabled')
        self.exit_rebind_btn.config(state='disabled')

        # Start listening for key press
        listener = pynput_keyboard.Listener(on_press=self.on_key_press)
        listener.start()

    def on_key_press(self, key):
        """Handle key press during rebinding"""
        if self.recording_hotkey is None:
            return False

        try:
            # Get key name
            if hasattr(key, 'name'):
                key_name = key.name
            elif hasattr(key, 'char'):
                key_name = key.char
            else:
                key_name = str(key).replace('key.', '')

            # Unregister old hotkey
            old_key = self.hotkeys[self.recording_hotkey]
            try:
                keyboard.remove_hotkey(old_key)
            except:
                pass

            # Update hotkey
            self.hotkeys[self.recording_hotkey] = key_name

            # Update label
            if self.recording_hotkey == 'toggle_loop':
                self.loop_key_label.config(text=key_name.upper())
            elif self.recording_hotkey == 'toggle_overlay':
                self.overlay_key_label.config(text=key_name.upper())
            elif self.recording_hotkey == 'exit':
                self.exit_key_label.config(text=key_name.upper())

            # Re-register hotkeys
            self.register_hotkeys()

            self.status_msg.config(text=f"Hotkey updated to '{key_name.upper()}'", foreground="green")

            # Re-enable buttons
            self.loop_rebind_btn.config(state='normal')
            self.overlay_rebind_btn.config(state='normal')
            self.exit_rebind_btn.config(state='normal')

            self.recording_hotkey = None
            return False  # Stop listener

        except Exception as e:
            self.status_msg.config(text=f"Error: {str(e)}", foreground="red")
            self.recording_hotkey = None
            return False

    def register_hotkeys(self):
        """Register all hotkeys"""
        try:
            keyboard.unhook_all()
            keyboard.add_hotkey(self.hotkeys['toggle_loop'], self.toggle_main_loop)
            keyboard.add_hotkey(self.hotkeys['toggle_overlay'], self.toggle_overlay)
            keyboard.add_hotkey(self.hotkeys['exit'], self.exit_app)
        except Exception as e:
            print(f"Error registering hotkeys: {e}")

    def toggle_main_loop(self):
        """Toggle the main loop on/off"""
        new_state = not self.main_loop_active

        if new_state:
            # We're turning the loop ON. If Auto Purchase is active, ensure points are set.
            if getattr(self, 'auto_purchase_var', None) and self.auto_purchase_var.get():
                pts = getattr(self, 'point_coords', {})
                missing = [i for i in (1, 2, 3, 4) if not pts.get(i)]
                if missing:
                    messagebox.showwarning("Auto Purchase: Points missing",
                                        f"Please set Point(s) {missing} before starting Auto Purchase.")
                    return

            # Reset purchase counter when starting the loop
            self.purchase_counter = 0

        # Apply new state
        self.main_loop_active = new_state

        if self.main_loop_active:
            self.loop_status.config(text="Main Loop: ON", foreground="#ffffff")
            # Start the main loop in a separate thread
            self.main_loop_thread = threading.Thread(target=self.main_loop, daemon=True)
            self.main_loop_thread.start()
        else:
            self.loop_status.config(text="Main Loop: OFF", foreground="#55aaff")
            # Release mouse button if it's being held when stopping
            if self.is_clicking:
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                self.is_clicking = False
            # Reset PD controller state
            self.previous_error = 0

    def check_and_purchase(self):
        """Check if we need to auto-purchase and run sequence if needed"""
        if getattr(self, 'auto_purchase_var', None) and self.auto_purchase_var.get():
            self.purchase_counter += 1
            loops_needed = int(getattr(self, 'loops_per_purchase', 1)) if getattr(self, 'loops_per_purchase', None) is not None else 1

            print(f"Purchase counter: {self.purchase_counter}/{loops_needed}")
            if self.purchase_counter >= max(1, loops_needed):
                print("Triggering auto-purchase sequence...")
                try:
                    self.perform_auto_purchase_sequence()
                except Exception as e:
                    print(f"Error during auto-purchase: {e}")
                self.purchase_counter = 0

    def cast_line(self):
        """Perform the casting action: hold click for 1 second then release"""
        print("Casting line...")
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        threading.Event().wait(1.0)  # Hold for 1 second
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        self.is_clicking = False
        print("Line cast")

    def main_loop(self):
        """Main loop that runs when activated"""
        print("Main loop started")

        # Target color #55aaff in RGB
        target_color = (0x55, 0xaa, 0xff)  # RGB format
        dark_color = (0x19, 0x19, 0x19)
        white_color = (0xff, 0xff, 0xff)

        import time

        # Initialize mss screen capture
        if self.sct is None:
            self.sct = mss.mss()

        try:
            # Perform initial auto-purchase sequence if enabled
            if getattr(self, 'auto_purchase_var', None) and self.auto_purchase_var.get():
                print("Running initial auto-purchase...")
                try:
                    self.perform_auto_purchase_sequence()
                except Exception as e:
                    print(f"Error during initial auto-purchase: {e}")

            # Perform initial cast
            self.cast_line()

            last_detection_time = time.time()
            was_detecting = False

            print("Entering main detection loop...")
            while self.main_loop_active:
                # Get the overlay area coordinates
                x = self.overlay_area['x']
                y = self.overlay_area['y']
                width = self.overlay_area['width']
                height = self.overlay_area['height']
                
                # Capture the screen area using mss
                region = {
                    'left': x,
                    'top': y,
                    'width': width,
                    'height': height
                }

                img = self.sct.grab(region)
                img_array = np.array(img)

                if img_array.size == 0:
                    threading.Event().wait(0.01)
                    continue

                # Find point 1 (left edge) - scan left to right, top to bottom
                point1_x = None
                point1_y = None

                found_first = False
                for row_idx in range(height):
                    for col_idx in range(width):
                        # Get pixel color (BGRA format from mss)
                        b, g, r, a = img_array[row_idx, col_idx, 0:4]

                        # Check if it matches target color #55aaff
                        if r == target_color[0] and g == target_color[1] and b == target_color[2]:
                            point1_x = x + col_idx
                            point1_y = y + row_idx
                            found_first = True
                            break
                    if found_first:
                        break

                if not found_first:
                    # No color found - check for timeout
                    current_time = time.time()

                    if was_detecting:
                        # Just lost detection - wait before re-casting
                        print("Lost detection, waiting...")
                        threading.Event().wait(self.wait_after_loss)
                        was_detecting = False
                        # Check if we need to purchase before casting
                        self.check_and_purchase()
                        self.cast_line()
                        last_detection_time = time.time()

                    elif current_time - last_detection_time > self.scan_timeout:
                        # Timeout - re-cast
                        print("Scan timeout, re-casting...")
                        # Check if we need to purchase before casting
                        self.check_and_purchase()
                        self.cast_line()
                        last_detection_time = time.time()

                    threading.Event().wait(0.1)
                    continue

                # Find point 2 (right edge) - scan right to left on the same Y coordinate
                point2_x = None
                row_idx = point1_y - y  # Convert back to relative row index

                for col_idx in range(width - 1, -1, -1):  # Scan from right to left
                    # Get pixel color (BGRA format)
                    b, g, r, a = img_array[row_idx, col_idx, 0:4]

                    # Check if it matches target color #55aaff
                    if r == target_color[0] and g == target_color[1] and b == target_color[2]:
                        point2_x = x + col_idx
                        break

                if point2_x is None:
                    # Didn't find second point, wait and continue
                    threading.Event().wait(0.1)
                    continue

                # Create initial width-only area
                temp_area_x = point1_x
                temp_area_width = point2_x - point1_x + 1

                # Now scan for #191919 to find the real height
                # Get temp_area from main frame (already captured)
                temp_x_offset = temp_area_x - x
                temp_img = img_array[:, temp_x_offset:temp_x_offset+temp_area_width]

                # Target color #191919 in RGB
                dark_color = (0x19, 0x19, 0x19)

                # Scan top to bottom for first #191919
                top_y = None
                for row_idx in range(height):
                    found_dark = False
                    for col_idx in range(temp_area_width):
                        b, g, r, a = temp_img[row_idx, col_idx, 0:4]
                        if r == dark_color[0] and g == dark_color[1] and b == dark_color[2]:
                            top_y = y + row_idx
                            found_dark = True
                            break
                    if found_dark:
                        break

                # Scan bottom to top for last #191919
                bottom_y = None
                for row_idx in range(height - 1, -1, -1):
                    found_dark = False
                    for col_idx in range(temp_area_width):
                        b, g, r, a = temp_img[row_idx, col_idx, 0:4]
                        if r == dark_color[0] and g == dark_color[1] and b == dark_color[2]:
                            bottom_y = y + row_idx
                            found_dark = True
                            break
                    if found_dark:
                        break

                if top_y is None or bottom_y is None:
                    threading.Event().wait(0.1)
                    continue

                # Create the real_area with proper height
                self.real_area = {
                    'x': temp_area_x,
                    'y': top_y,
                    'width': temp_area_width,
                    'height': bottom_y - top_y + 1
                }

                # Now scan the real_area for #ffffff
                real_x = self.real_area['x']
                real_y = self.real_area['y']
                real_width = self.real_area['width']
                real_height = self.real_area['height']

                # Extract real_area from main frame
                real_x_offset = real_x - x
                real_y_offset = real_y - y
                real_img = img_array[real_y_offset:real_y_offset+real_height, real_x_offset:real_x_offset+real_width]

                # Target color #ffffff in RGB
                white_color = (0xff, 0xff, 0xff)

                # Scan top to bottom, left to right for #ffffff to find the top
                white_top_y = None
                white_bottom_y = None

                for row_idx in range(real_height):
                    for col_idx in range(real_width):
                        # Get pixel color (BGRA format)
                        b, g, r, a = real_img[row_idx, col_idx, 0:4]

                        # Check if it matches #ffffff
                        if r == white_color[0] and g == white_color[1] and b == white_color[2]:
                            white_top_y = real_y + row_idx
                            break

                    if white_top_y is not None:
                        break

                # Scan bottom to top to find the bottom of #ffffff
                for row_idx in range(real_height - 1, -1, -1):
                    for col_idx in range(real_width):
                        # Get pixel color (BGRA format)
                        b, g, r, a = real_img[row_idx, col_idx, 0:4]

                        # Check if it matches #ffffff
                        if r == white_color[0] and g == white_color[1] and b == white_color[2]:
                            white_bottom_y = real_y + row_idx
                            break
                            
                    if white_bottom_y is not None:
                        break

                # Calculate the white height and max_gap
                if white_top_y is not None and white_bottom_y is not None:
                    white_height = white_bottom_y - white_top_y + 1
                    max_gap = white_height * 2
                else:
                    max_gap = 3  # Default fallback

                # Now find the section of consecutive #191919 pixels in the real_area
                # Scan column by column to find continuous dark sections
                # Allow gaps based on white_height (white_height * 2)

                dark_sections = []
                current_section_start = None
                gap_counter = 0

                for row_idx in range(real_height):
                    # Check if this row has #191919
                    has_dark = False
                    for col_idx in range(real_width):
                        b, g, r, a = real_img[row_idx, col_idx, 0:4]

                        if r == dark_color[0] and g == dark_color[1] and b == dark_color[2]:
                            has_dark = True
                            break

                    if has_dark:
                        # Reset gap counter and continue/start section
                        gap_counter = 0
                        if current_section_start is None:
                            current_section_start = real_y + row_idx
                    else:
                        # No dark pixel in this row
                        if current_section_start is not None:
                            gap_counter += 1
                            # Only end section if gap exceeds max_gap
                            if gap_counter > max_gap:
                                section_end = real_y + row_idx - gap_counter
                                dark_sections.append({
                                    'start': current_section_start,
                                    'end': section_end,
                                    'middle': (current_section_start + section_end) // 2
                                })
                                current_section_start = None
                                gap_counter = 0

                # Handle case where dark section extends to the bottom
                if current_section_start is not None:
                    section_end = real_y + real_height - 1 - gap_counter
                    dark_sections.append({
                        'start': current_section_start,
                        'end': section_end,
                        'middle': (current_section_start + section_end) // 2
                    })

                # Find the largest dark section (the middle one)
                if dark_sections and white_top_y is not None:
                    # Successfully detected - update tracking variables
                    was_detecting = True
                    last_detection_time = time.time()

                    # Calculate the size of each section and find the largest
                    for section in dark_sections:
                        section['size'] = section['end'] - section['start'] + 1

                    # Sort by size and get the largest
                    largest_section = max(dark_sections, key=lambda s: s['size'])

                    # Output only the two Y coordinates
                    print(f"y1:{white_top_y}")
                    print(f"y2:{largest_section['middle']}")

                    # PD controller logic with resolution-independent error calculation
                    # Normalize error by the height of the detection area to make it resolution-independent
                    # Error is positive when middle is below white (need to accelerate up)
                    # Error is negative when middle is above white (need to accelerate down)
                    raw_error = largest_section['middle'] - white_top_y

                    # Normalize by real_height to get error as a ratio (resolution-independent)
                    # This ensures the same kp/kd values work across all resolutions
                    normalized_error = raw_error / real_height if real_height > 0 else raw_error

                    # Calculate PD terms using normalized error
                    derivative = normalized_error - self.previous_error
                    self.previous_error = normalized_error

                    # PD output
                    pd_output = (self.kp * normalized_error) + (self.kd * derivative)

                    print(f"Error: {raw_error}px ({normalized_error:.3f} normalized), PD Output: {pd_output:.2f}")

                    # Decide whether to hold or release based on PD output
                    # Positive error/output = middle is below, need to go up = hold click
                    # Negative error/output = middle is above, need to go down = release click
                    if pd_output > 0:
                        # Need to accelerate up - hold left click
                        if not self.is_clicking:
                            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                            self.is_clicking = True
                    else:
                        # Need to accelerate down - release left click
                        if self.is_clicking:
                            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                            self.is_clicking = False
                    print()

                # Small delay to prevent CPU overuse
                threading.Event().wait(0.01)

        finally:
            # Close mss connection if needed
            if self.sct:
                try:
                    self.sct.close()
                except:
                    pass

        print("Main loop stopped")

    def toggle_overlay(self):
        """Toggle the overlay on/off"""
        self.overlay_active = not self.overlay_active

        if self.overlay_active:
            self.overlay_status.config(text="Overlay: ON", foreground="#ffffff")
            self.create_overlay()
            print(f"Overlay activated at: {self.overlay_area}")
        else:
            self.overlay_status.config(text="Overlay: OFF", foreground="#55aaff")
            self.destroy_overlay()
            print(f"Overlay deactivated. Saved area: {self.overlay_area}")

    def create_overlay(self):
        """Create a draggable, resizable overlay window"""
        if self.overlay_window is not None:
            return

        # Create overlay window
        self.overlay_window = tk.Toplevel(self.root)

        # Remove window decorations (title bar, borders)
        self.overlay_window.overrideredirect(True)

        # Set window properties
        self.overlay_window.attributes('-alpha', 0.5)  # Semi-transparent
        self.overlay_window.attributes('-topmost', True)  # Always on top

        # Remove minimum size restrictions
        self.overlay_window.minsize(1, 1)

        # Set geometry from saved area
        geometry = f"{self.overlay_area['width']}x{self.overlay_area['height']}+{self.overlay_area['x']}+{self.overlay_area['y']}"
        self.overlay_window.geometry(geometry)

        # Create frame with border (using #55aaff color)
        frame = tk.Frame(self.overlay_window, bg="#55aaff", highlightthickness=2, highlightbackground="#55aaff")
        frame.pack(fill=tk.BOTH, expand=True)

        # Resize and drag data
        self.overlay_drag_data = {"x": 0, "y": 0, "resize_edge": None}

        # Bind mouse events for dragging and resizing
        self.overlay_window.bind("<ButtonPress-1>", self.start_overlay_action)
        self.overlay_window.bind("<B1-Motion>", self.overlay_motion)
        self.overlay_window.bind("<Motion>", self.update_cursor)
        frame.bind("<ButtonPress-1>", self.start_overlay_action)
        frame.bind("<B1-Motion>", self.overlay_motion)
        frame.bind("<Motion>", self.update_cursor)

        # Bind configure events
        self.overlay_window.bind("<Configure>", self.on_overlay_configure)

    def get_resize_edge(self, x, y):
        """Determine which edge/corner is near the mouse"""
        width = self.overlay_window.winfo_width()
        height = self.overlay_window.winfo_height()
        edge_size = 10  # pixels from edge to trigger resize

        on_left = x < edge_size
        on_right = x > width - edge_size
        on_top = y < edge_size
        on_bottom = y > height - edge_size

        if on_top and on_left:
            return "nw"
        elif on_top and on_right:
            return "ne"
        elif on_bottom and on_left:
            return "sw"
        elif on_bottom and on_right:
            return "se"
        elif on_left:
            return "w"
        elif on_right:
            return "e"
        elif on_top:
            return "n"
        elif on_bottom:
            return "s"
        return None

    def update_cursor(self, event):
        """Update cursor based on position"""
        edge = self.get_resize_edge(event.x, event.y)
        cursor_map = {
            "nw": "size_nw_se",
            "ne": "size_ne_sw",
            "sw": "size_ne_sw",
            "se": "size_nw_se",
            "n": "size_ns",
            "s": "size_ns",
            "e": "size_we",
            "w": "size_we",
            None: "arrow"
        }
        self.overlay_window.config(cursor=cursor_map.get(edge, "arrow"))

    def start_overlay_action(self, event):
        """Start dragging or resizing the overlay"""
        self.overlay_drag_data["x"] = event.x
        self.overlay_drag_data["y"] = event.y
        self.overlay_drag_data["resize_edge"] = self.get_resize_edge(event.x, event.y)
        self.overlay_drag_data["start_width"] = self.overlay_window.winfo_width()
        self.overlay_drag_data["start_height"] = self.overlay_window.winfo_height()
        self.overlay_drag_data["start_x"] = self.overlay_window.winfo_x()
        self.overlay_drag_data["start_y"] = self.overlay_window.winfo_y()

    def overlay_motion(self, event):
        """Handle dragging or resizing the overlay"""
        edge = self.overlay_drag_data["resize_edge"]

        if edge is None:
            # Dragging
            x = self.overlay_window.winfo_x() + event.x - self.overlay_drag_data["x"]
            y = self.overlay_window.winfo_y() + event.y - self.overlay_drag_data["y"]
            self.overlay_window.geometry(f"+{x}+{y}")
        else:
            # Resizing
            dx = event.x - self.overlay_drag_data["x"]
            dy = event.y - self.overlay_drag_data["y"]

            new_width = self.overlay_drag_data["start_width"]
            new_height = self.overlay_drag_data["start_height"]
            new_x = self.overlay_drag_data["start_x"]
            new_y = self.overlay_drag_data["start_y"]

            # Handle horizontal resize
            if 'e' in edge:
                new_width = max(1, self.overlay_drag_data["start_width"] + dx)
            elif 'w' in edge:
                new_width = max(1, self.overlay_drag_data["start_width"] - dx)
                new_x = self.overlay_drag_data["start_x"] + dx

            # Handle vertical resize
            if 's' in edge:
                new_height = max(1, self.overlay_drag_data["start_height"] + dy)
            elif 'n' in edge:
                new_height = max(1, self.overlay_drag_data["start_height"] - dy)
                new_y = self.overlay_drag_data["start_y"] + dy

            self.overlay_window.geometry(f"{new_width}x{new_height}+{new_x}+{new_y}")

    def on_overlay_configure(self, event=None):
        """Save overlay position and size when it changes"""
        if self.overlay_window is not None:
            self.overlay_area['x'] = self.overlay_window.winfo_x()
            self.overlay_area['y'] = self.overlay_window.winfo_y()
            self.overlay_area['width'] = self.overlay_window.winfo_width()
            self.overlay_area['height'] = self.overlay_window.winfo_height()

    def destroy_overlay(self):
        """Destroy the overlay window"""
        if self.overlay_window is not None:
            # Save final position before destroying
            self.overlay_area['x'] = self.overlay_window.winfo_x()
            self.overlay_area['y'] = self.overlay_window.winfo_y()
            self.overlay_area['width'] = self.overlay_window.winfo_width()
            self.overlay_area['height'] = self.overlay_window.winfo_height()

            self.overlay_window.destroy()
            self.overlay_window = None

    def exit_app(self):
        """Exit the application"""
        print("Exiting application...")

        # Stop main loop if running
        self.main_loop_active = False

        # Destroy overlay if open
        if self.overlay_window is not None:
            try:
                self.overlay_window.destroy()
                self.overlay_window = None
            except:
                pass

        # Unhook all keyboard listeners
        try:
            keyboard.unhook_all()
        except:
            pass

        # Destroy root window and exit
        try:
            self.root.destroy()
        except:
            pass

        sys.exit(0)

def main():
    root = tk.Tk()
    app = HotkeyGUI(root)

    # Handle window close
    root.protocol("WM_DELETE_WINDOW", app.exit_app)

    root.mainloop()

if __name__ == "__main__":
    main()
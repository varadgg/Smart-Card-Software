# --- app.py ---
# Final All-in-One ID Card Printer Studio
#
# Version 6.2 - Final version with dynamic password and universal print dialog.
# - Password is now taken from the GUI field, not hardcoded.
# - Print function opens the OS default print dialog instead of using a fixed printer name.
# - GUI includes input fields for Name (Marathi), Aadhaar No, and Address (Marathi).
# - Automatically extracts English address from PDF.
# - User can upload a photo manually.
# - Extracts QR code from the PDF.
# - Uses specific asset images for headers and footers.

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk, ImageDraw, ImageFont
import fitz  # PyMuPDF
import re
import os
import platform
import io
import textwrap

# ==============================================================================
# 1. DATA EXTRACTION LOGIC (Merged Automatic Address Extraction)
# ==============================================================================
def is_devanagari(char):
    """Checks if a character is in the Devanagari Unicode range."""
    return '\u0900' <= char <= '\u097F'

def extract_data_from_pdf(pdf_path, password):
    """
    Extracts QR, Eng Name, DOB, Gender, AND ADDRESSES from the PDF.
    Manual fields in the GUI will override some of this data.
    """
    try:
        doc = fitz.open(pdf_path)
        if doc.is_encrypted:
            if not doc.authenticate(password): raise ValueError("Invalid password.")
        
        page = doc[0]
        full_text = page.get_text("text")
        extracted_data = {}

        # --- Extract QR Code Only ---
        images_info = page.get_images(full=True)
        qrcode_xref = None
        for img_info in images_info:
            pix = fitz.Pixmap(doc, img_info[0])
            if pix.width > 50 and 0.95 <= (pix.width / pix.height) <= 1.05:
                qrcode_xref = img_info[0]
                break
            pix = None
        
        if qrcode_xref is None:
            raise ValueError("QR code extraction failed. Could not find a square-shaped image.")
        
        qrcode_pix = fitz.Pixmap(doc, qrcode_xref)
        extracted_data['qrcode_bytes'] = qrcode_pix.tobytes("png")
        qrcode_pix = None
        
        # --- Extract Basic Details ---
        extracted_data['dob'] = (re.search(r'DOB:\s*(\d{2}/\d{2}/\d{4})', full_text, re.I) or ['','N/A'])[1]
        
        gender_en = (re.search(r'Gender\s*:\s*(\w+)', full_text, re.I) or [None, None])[1]
        if not gender_en:
            if re.search(r'\bMALE\b', full_text, re.I): gender_en = 'MALE'
            elif re.search(r'\bFEMALE\b', full_text, re.I): gender_en = 'FEMALE'
        extracted_data['gender'] = (gender_en or '').upper()

        # --- Extract Names and Addresses using Contextual Blocks ---
        text_blocks = page.get_text("blocks")
        extracted_data.update({'name': "Name Not Found", 'address': "Address Not Found", 'address_mr': "पत्ता सापडला नाही"})

        for block in text_blocks:
            block_text = block[4].strip()
            
            if "DOB:" in block_text or "Date of Birth" in block_text:
                lines = block_text.split('\n')
                english_names = [line.strip() for line in lines if line.strip() and line.isascii() and not any(word in line.upper() for word in ['DOB', 'GENDER', 'YEAR', 'DATE', 'BIRTH'])]
                if english_names:
                    extracted_data['name'] = english_names[0]

            if "Address:" in block_text or "पत्ता" in block_text:
                address_full_text = block[4].split("Address:", 1)[-1].split("पत्ता", 1)[-1]
                regional_start_index = -1
                for i, char in enumerate(address_full_text):
                    if not char.isascii():
                        regional_start_index = i
                        break
                
                if regional_start_index != -1:
                    eng_address = address_full_text[:regional_start_index]
                    regional_address = address_full_text[regional_start_index:]
                    extracted_data['address'] = ' '.join(eng_address.split())
                    extracted_data['address_mr'] = ' '.join(regional_address.split())
                else:
                    extracted_data['address'] = ' '.join(address_full_text.split())

        doc.close()
        return extracted_data
    except Exception as e:
        if 'doc' in locals() and doc: doc.close()
        raise e

# ==============================================================================
# 2. ID CARD GENERATION LOGIC (Takes manual data)
# ==============================================================================
def create_id_card(data, photo_path):
    CARD_WIDTH, CARD_HEIGHT = 1011, 638
    BG_COLOR = (255, 255, 255)
    
    HEADER_HEIGHT = 110
    FOOTER_HEIGHT = 110

    try:
        font_eng_reg = ImageFont.truetype("fonts/arial.ttf", 24)
        font_eng_bold = ImageFont.truetype("fonts/arialbd.ttf", 28)
        font_marathi = ImageFont.truetype("fonts/Nirmala.ttf", 28)
        font_bilingual_label = ImageFont.truetype("fonts/Nirmala.ttf", 26)
        font_aadhaar = ImageFont.truetype("fonts/arialbd.ttf", 38)
    except IOError:
        raise IOError("A required font was not found. Ensure all required fonts are in the 'fonts/' folder.")

    try:
        front_header = Image.open("assets/front_header.png")
        front_footer = Image.open("assets/front_fotter.png")
        back_header = Image.open("assets/back_header.png")
        back_footer = Image.open("assets/back_fotter.png")
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Asset file not found: {e}. Make sure all header/footer images are in the 'assets' folder.")

    # ==================== CREATE FRONT OF THE CARD ====================
    front_card = Image.new('RGB', (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    
    front_header = front_header.resize((CARD_WIDTH, HEADER_HEIGHT))
    front_card.paste(front_header, (0, 0), front_header)
    front_footer = front_footer.resize((CARD_WIDTH, FOOTER_HEIGHT))
    front_card.paste(front_footer, (0, CARD_HEIGHT - FOOTER_HEIGHT), front_footer)

    photo = Image.open(photo_path).resize((260, 320))
    front_card.paste(photo, (40, 140))

    qrcode = Image.open(io.BytesIO(data['qrcode_bytes'])).resize((240, 240))
    front_card.paste(qrcode, (CARD_WIDTH - 280, 190))

    draw_front = ImageDraw.Draw(front_card)
    text_x_start = 330
    
    draw_front.text((text_x_start, 180), data.get('name_mr', ''), font=font_marathi, fill="black")
    draw_front.text((text_x_start, 220), data.get('name', ''), font=font_eng_bold, fill="black")
    
    draw_front.text((text_x_start, 270), f"Date of Birth: {data.get('dob', 'N/A')}", font=font_eng_reg, fill="black")
    
    gender_mr = 'पुरुष' if data.get('gender') == 'MALE' else 'स्त्री' if data.get('gender') == 'FEMALE' else ''
    gender_values = f"{gender_mr} / {data.get('gender', '')}"
    draw_front.text((text_x_start, 310), gender_values, font=font_bilingual_label, fill="black")
    
    draw_front.text((360, 485), data.get('aadhaar_no', ''), font=font_aadhaar, fill="black")
    front_card.save("id_card_front.png")

    # ==================== CREATE BACK OF THE CARD ====================
    back_card = Image.new('RGB', (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    
    back_header = back_header.resize((CARD_WIDTH, HEADER_HEIGHT))
    back_card.paste(back_header, (0, 0), back_header)
    back_footer = back_footer.resize((CARD_WIDTH, FOOTER_HEIGHT))
    back_card.paste(back_footer, (0, CARD_HEIGHT - FOOTER_HEIGHT), back_footer)

    draw_back = ImageDraw.Draw(back_card)
    
    eng_addr_lines = textwrap.wrap(f"Address: {data.get('address', '')}", width=40)
    y_text = 150
    for line in eng_addr_lines:
        draw_back.text((40, y_text), line, font=font_eng_reg, fill="black")
        y_text += 30

    mar_addr_lines = textwrap.wrap(f"पत्ता: {data.get('address_mr', '')}", width=35)
    y_text = 150
    for line in mar_addr_lines:
        draw_back.text((520, y_text), line, font=font_marathi, fill="black")
        y_text += 35
        
    draw_back.text((360, 485), data.get('aadhaar_no', ''), font=font_aadhaar, fill="black")
    back_card.save("id_card_back.png")
    
    return "id_card_front.png", "id_card_back.png"

# ==============================================================================
# 3. PRINTER LOGIC (Updated for Universal Print Dialog)
# ==============================================================================
def print_image(image_path):
    """
    Prints an image file by opening the default OS print dialog.
    This is more universal than specifying a printer name.
    """
    if not os.path.exists(image_path):
        messagebox.showerror("Error", f"Image path '{image_path}' not found.")
        return

    try:
        if platform.system() == "Windows":
            # This command opens the image in the default viewer and brings up the print dialog.
            os.startfile(image_path, "print")
        elif platform.system() == "Darwin":  # macOS
            os.system(f"open -a 'Preview' {image_path} && osascript -e 'tell application \"Preview\" to print the first document'")
        else:  # Linux
            # 'lp' or 'lpr' can be used, but they often print directly without a dialog.
            # A better approach for Linux is to open with a viewer that supports printing.
            # We'll try 'xdg-open' which is the standard way to open files.
            os.system(f"xdg-open {image_path}")
            messagebox.showinfo("Print", "Your image has been opened in the default viewer. Please use its print function (Ctrl+P).")

    except Exception as e:
        messagebox.showerror("Printing Failed", f"Could not open the print dialog. Error: {e}")

# ==============================================================================
# 4. GUI APPLICATION CLASS (Updated for new password and print logic)
# ==============================================================================
class IDCardApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ID Card Studio (Manual Entry)")
        self.geometry("950x750")
        self.pdf_path, self.photo_path, self.front_image_path, self.back_image_path = None, None, None, None
        
        control_frame = ttk.Frame(self, padding="10")
        control_frame.pack(fill=tk.X, side=tk.TOP)
        
        self.select_photo_button = ttk.Button(control_frame, text="1. Upload Photo", command=self.select_photo_file)
        self.select_photo_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.photo_path_label = ttk.Label(control_frame, text="No photo selected.", width=20, anchor="w")
        self.photo_path_label.pack(side=tk.LEFT, padx=5, pady=5)

        ttk.Label(control_frame, text="PDF Password:").pack(side=tk.LEFT, padx=(10, 5), pady=5)
        self.password_entry = ttk.Entry(control_frame, show="*", width=15)
        self.password_entry.pack(side=tk.LEFT, padx=5, pady=5)

        entry_frame = ttk.LabelFrame(self, text="Manual Data Entry", padding="10")
        entry_frame.pack(fill=tk.X, side=tk.TOP, padx=10, pady=5)

        ttk.Label(entry_frame, text="Name in Marathi:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.name_mr_entry = ttk.Entry(entry_frame, width=40)
        self.name_mr_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        ttk.Label(entry_frame, text="Aadhaar Number:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.aadhaar_no_entry = ttk.Entry(entry_frame, width=40)
        self.aadhaar_no_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=2)

        ttk.Label(entry_frame, text="Address in Marathi:").grid(row=0, column=2, sticky="w", padx=15, pady=2)
        self.address_mr_entry = ttk.Entry(entry_frame, width=60)
        self.address_mr_entry.grid(row=0, column=3, sticky="ew", padx=5, pady=2)

        entry_frame.columnconfigure(1, weight=1)
        entry_frame.columnconfigure(3, weight=2)

        action_frame = ttk.Frame(self, padding="10")
        action_frame.pack(fill=tk.X, side=tk.TOP)
        
        self.select_button = ttk.Button(action_frame, text="2. Select PDF & Generate", command=self.select_and_process_pdf)
        self.select_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.print_button = ttk.Button(action_frame, text="3. Print ID Card", command=self.print_card_action, state="disabled")
        self.print_button.pack(side=tk.LEFT, padx=5, pady=5)

        self.status_label = ttk.Label(action_frame, text="Upload a photo and fill in the details to begin.")
        self.status_label.pack(side=tk.LEFT, padx=10, pady=5)
        
        preview_frame = ttk.Frame(self, padding="10")
        preview_frame.pack(fill=tk.BOTH, expand=True)
        self.front_preview_label = ttk.Label(preview_frame, text="Front Preview", compound="top", relief="solid", borderwidth=1)
        self.front_preview_label.pack(side=tk.LEFT, padx=10, expand=True, fill=tk.BOTH)
        self.back_preview_label = ttk.Label(preview_frame, text="Back Preview", compound="top", relief="solid", borderwidth=1)
        self.back_preview_label.pack(side=tk.RIGHT, padx=10, expand=True, fill=tk.BOTH)

    def select_photo_file(self):
        file_path = filedialog.askopenfilename(title="Select a Photo", filetypes=(("Image Files", "*.jpg *.jpeg *.png"), ("All files", "*.*")))
        if file_path:
            self.photo_path = file_path
            self.photo_path_label.config(text=os.path.basename(file_path))

    def select_and_process_pdf(self):
        if not self.photo_path:
            messagebox.showerror("Error", "Please upload a photo.")
            return
        manual_name_mr = self.name_mr_entry.get()
        manual_aadhaar_no = self.aadhaar_no_entry.get()
        manual_address_mr = self.address_mr_entry.get()
        if not all([manual_name_mr, manual_aadhaar_no, manual_address_mr]):
            messagebox.showerror("Error", "Please fill in all manual entry fields.")
            return

        self.pdf_path = filedialog.askopenfilename(title="Select PDF", filetypes=(("PDF Files", "*.pdf"),))
        if not self.pdf_path: return
        
        # --- PASSWORD IS NOW TAKEN FROM THE GUI FIELD ---
        password = self.password_entry.get()
        
        self.status_label.config(text=f"Processing: {os.path.basename(self.pdf_path)}...")
        self.update_idletasks()
        try:
            data = extract_data_from_pdf(self.pdf_path, password)
            
            data['name_mr'] = manual_name_mr
            data['aadhaar_no'] = manual_aadhaar_no
            data['address_mr'] = manual_address_mr

            self.front_image_path, self.back_image_path = create_id_card(data, self.photo_path)
            self.update_previews()
            self.status_label.config(text="Card generated successfully! Ready to print.")
            self.print_button.config(state="normal")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")
            self.status_label.config(text="Processing failed. Check password, file format, or asset files.")
            self.print_button.config(state="disabled")

    def update_previews(self):
        preview_width = (self.winfo_width() // 2) - 40
        front_img = Image.open(self.front_image_path)
        ratio = front_img.height / front_img.width
        new_height = int(preview_width * ratio)
        front_img_resized = front_img.resize((preview_width, new_height))
        self.front_photo_img = ImageTk.PhotoImage(front_img_resized)
        self.front_preview_label.config(image=self.front_photo_img, text="Front Preview")
        
        back_img = Image.open(self.back_image_path)
        back_img_resized = back_img.resize((preview_width, new_height))
        self.back_photo_img = ImageTk.PhotoImage(back_img_resized)
        self.back_preview_label.config(image=self.back_photo_img, text="Back Preview")

    def print_card_action(self):
        # --- PRINT FUNCTION NOW OPENS DIALOG, NOT A SPECIFIC PRINTER ---
        if not self.front_image_path or not self.back_image_path:
            messagebox.showwarning("Warning", "No card images to print.")
            return
        if messagebox.askokcancel("Print Front", "The print dialog for the FRONT of the card will now open. Please select your printer and set the correct properties (e.g., PVC card size, tray)."):
            print_image(self.front_image_path)
        if messagebox.askokcancel("Print Back", "Please flip the card in the printer tray.\n\nClick OK to open the print dialog for the BACK of the card."):
            print_image(self.back_image_path)
        self.status_label.config(text="Print jobs sent.")

# ==============================================================================
# 5. SCRIPT EXECUTION
# ==============================================================================
if __name__ == "__main__":
    app = IDCardApp()
    app.mainloop()
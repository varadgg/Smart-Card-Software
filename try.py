# --- app.py ---

# Final All-in-One ID Card Printer Studio
#
# Version 4.3 - Improved Marathi text extraction and font handling
# - Properly extracts and displays Marathi name, date of birth, and gender
# - Uses KF-Kiran font for all Marathi text
# - Marathi name is positioned above English name
# - User can upload a photo manually
# - Handles password-protected PDFs
# - Extracts all text data (English and Marathi)
# - Extracts existing QR code from the PDF
# - Uses specific asset images for headers and footers

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
# 1. DATA EXTRACTION LOGIC (Improved Marathi text extraction)
# ==============================================================================
def is_devanagari(char):
    """Checks if a character is in the Devanagari Unicode range."""
    return '\u0900' <= char <= '\u097F'

def extract_data_from_pdf(pdf_path, password):
    """
    Extracts all text data and the QR code from a password-protected Aadhaar PDF.
    Improved Marathi text extraction for name, date of birth, and gender.
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
            # QR codes are square. Check for aspect ratio close to 1.
            if pix.width > 50 and 0.95 <= (pix.width / pix.height) <= 1.05:
                qrcode_xref = img_info[0]
                break
            pix = None # Cleanup
        
        if qrcode_xref is None:
            raise ValueError("QR code extraction failed. Could not find a square-shaped image.")
        
        qrcode_pix = fitz.Pixmap(doc, qrcode_xref)
        extracted_data['qrcode_bytes'] = qrcode_pix.tobytes("png")
        qrcode_pix = None # Cleanup
        
        # --- Extract English Text using Regex ---
        extracted_data['dob'] = (re.search(r'DOB:\s*(\d{2}/\d{2}/\d{4})', full_text, re.I) or ['','N/A'])[1]
        extracted_data['gender'] = (re.search(r'Gender:\s*(\w+)', full_text, re.I) or ['','N/A'])[1].upper()
        extracted_data['aadhaar_no'] = (re.search(r'(\d{4}\s\d{4}\s\d{4})', full_text) or ['','N/A'])[1]

        # --- Extract Marathi text for Date of Birth and Gender ---
        marathi_dob = re.search(r'जन्म तारीख[:\s]*(\d{2}/\d{2}/\d{4})', full_text)
        if marathi_dob:
            extracted_data['dob_mr'] = marathi_dob.group(1)
        else:
            extracted_data['dob_mr'] = extracted_data['dob']  # Fallback to English DOB
        
        # Extract Marathi gender
        marathi_gender_match = re.search(r'लिंग[:\s]*(\S+)', full_text)
        if marathi_gender_match:
            gender_text = marathi_gender_match.group(1)
            if 'पुरुष' in gender_text:
                extracted_data['gender_mr'] = 'पुरुष'
            elif 'स्त्री' in gender_text:
                extracted_data['gender_mr'] = 'स्त्री'
            else:
                extracted_data['gender_mr'] = gender_text
        else:
            # Fallback: Translate English gender to Marathi
            if extracted_data['gender'] == 'MALE':
                extracted_data['gender_mr'] = 'पुरुष'
            elif extracted_data['gender'] == 'FEMALE':
                extracted_data['gender_mr'] = 'स्त्री'
            else:
                extracted_data['gender_mr'] = extracted_data['gender']

        # --- Extract Blocks of Text for Contextual Analysis (English/Marathi) ---
        text_blocks = page.get_text("blocks")
        
        # Fallbacks
        extracted_data.update({
            'name': "Name Not Found", 
            'address': "Address Not Found", 
            'name_mr': "नाव सापडले नाही", 
            'address_mr': "पत्ता सापडला नाही"
        })

        for block in text_blocks:
            block_text = block[4].strip()
            
            # Extract name (both English and Marathi)
            if "DOB:" in block_text or "जन्म तारीख" in block_text:
                lines = block_text.split('\n')
                
                # Extract Marathi name (lines with Devanagari characters)
                marathi_names = [line.strip() for line in lines if any(is_devanagari(c) for c in line) and not any(word in line for word in ['जन्म', 'तारीख', 'लिंग'])]
                if marathi_names:
                    extracted_data['name_mr'] = marathi_names[0]
                
                # Extract English name (lines without Devanagari characters, excluding labels)
                english_names = [line.strip() for line in lines if line.strip() and not any(is_devanagari(c) for c in line) and not any(word in line.upper() for word in ['DOB', 'GENDER', 'YEAR', 'DATE'])]
                if english_names:
                    extracted_data['name'] = english_names[0]

            # Extract address
            if "Address:" in block_text or "पत्ता" in block_text:
                address_full_text = block_text
                if "Address:" in address_full_text:
                    address_full_text = address_full_text.split("Address:", 1)[1]
                elif "पत्ता" in address_full_text:
                    address_full_text = address_full_text.split("पत्ता", 1)[1]
                
                # Separate English and Marathi addresses
                marathi_start_index = -1
                for i, char in enumerate(address_full_text):
                    if is_devanagari(char): 
                        marathi_start_index = i
                        break
                
                if marathi_start_index != -1:
                    eng_address = address_full_text[:marathi_start_index]
                    mar_address = address_full_text[marathi_start_index:]
                    extracted_data['address'] = ' '.join(eng_address.split())
                    extracted_data['address_mr'] = ' '.join(mar_address.split())
                else:
                    # If no Devanagari found, assume it's all English
                    extracted_data['address'] = ' '.join(address_full_text.split())

        doc.close()
        return extracted_data
    except Exception as e:
        if 'doc' in locals() and doc: doc.close()
        raise e

# ==============================================================================
# 2. ID CARD GENERATION LOGIC (Improved Marathi text positioning and font handling)
# ==============================================================================
def create_id_card(data, photo_path):
    CARD_WIDTH, CARD_HEIGHT = 1011, 638
    BG_COLOR = (255, 255, 255)
    
    # --- Define Header and Footer Heights for Symmetry ---
    HEADER_HEIGHT = 110
    FOOTER_HEIGHT = 110 # Set to the same as header

    # --- Load Fonts ---
    try:
        font_eng_reg = ImageFont.truetype("fonts/arial.ttf", 24)
        font_eng_bold = ImageFont.truetype("fonts/arialbd.ttf", 28)
        font_marathi = ImageFont.truetype("fonts/KF-Kiran.ttf", 28)
        font_marathi_small = ImageFont.truetype("fonts/KF-Kiran.ttf", 24)
        font_aadhaar = ImageFont.truetype("fonts/arialbd.ttf", 38)
    except IOError:
        raise IOError("A required font was not found. Ensure arial.ttf, arialbd.ttf, and KF-Kiran.ttf are in the 'fonts/' folder.")

    # --- Load Assets ---
    try:
        front_header = Image.open("assets/front_header.png")
        front_footer = Image.open("assets/front_fotter.png")
        back_header = Image.open("assets/back_header.png")
        back_footer = Image.open("assets/back_fotter.png")
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Asset file not found: {e}. Make sure all header/footer images are in the 'assets' folder.")

    # ==================== CREATE FRONT OF THE CARD ====================
    front_card = Image.new('RGB', (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    
    # Paste Header & Footer
    front_header = front_header.resize((CARD_WIDTH, HEADER_HEIGHT))
    front_card.paste(front_header, (0, 0), front_header)
    
    front_footer = front_footer.resize((CARD_WIDTH, FOOTER_HEIGHT))
    front_card.paste(front_footer, (0, CARD_HEIGHT - FOOTER_HEIGHT), front_footer) # Correctly aligned at the bottom

    # Paste Photo from user-provided file path
    photo = Image.open(photo_path).resize((260, 320))
    front_card.paste(photo, (40, 140))

    # Paste QR Code
    qrcode = Image.open(io.BytesIO(data['qrcode_bytes'])).resize((240, 240))
    front_card.paste(qrcode, (CARD_WIDTH - 280, 190))

    # Draw Text - Marathi name above English name
    draw_front = ImageDraw.Draw(front_card)
    text_x_start = 330
    
    # Marathi name positioned above English name (using KF-Kiran font)
    draw_front.text((text_x_start, 160), data.get('name_mr', ''), font=font_marathi, fill="black")
    draw_front.text((text_x_start, 200), data.get('name', ''), font=font_eng_bold, fill="black")
    
    # Date of Birth with both Marathi and English labels
    dob_label_text = "जन्म तारीख/DOB:"
    dob_value_text = data.get('dob_mr', data.get('dob', 'N/A'))
    
    # Draw Marathi label part
    draw_front.text((text_x_start, 250), dob_label_text, font=font_marathi_small, fill="black")
    
    # Measure Marathi label width to position English value correctly
    marathi_label_width = font_marathi_small.getlength(dob_label_text)
    draw_front.text((text_x_start + marathi_label_width + 5, 250), dob_value_text, font=font_eng_reg, fill="black")
    
    # Gender with both Marathi and English labels
    gender_label_text = "लिंग/Gender:"
    gender_value_text = f"{data.get('gender_mr', '')}/{data.get('gender', '')}"
    
    # Draw Marathi label part
    draw_front.text((text_x_start, 290), gender_label_text, font=font_marathi_small, fill="black")
    
    # Measure Marathi label width to position English value correctly
    marathi_gender_width = font_marathi_small.getlength(gender_label_text)
    draw_front.text((text_x_start + marathi_gender_width + 5, 290), gender_value_text, font=font_eng_reg, fill="black")
    
    # Aadhaar Number
    draw_front.text((360, 485), data.get('aadhaar_no', ''), font=font_aadhaar, fill="black")
    
    front_card.save("id_card_front.png")

    # ==================== CREATE BACK OF THE CARD ====================
    back_card = Image.new('RGB', (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    
    # Paste Header & Footer
    back_header = back_header.resize((CARD_WIDTH, HEADER_HEIGHT))
    back_card.paste(back_header, (0, 0), back_header)
    
    back_footer = back_footer.resize((CARD_WIDTH, FOOTER_HEIGHT))
    back_card.paste(back_footer, (0, CARD_HEIGHT - FOOTER_HEIGHT), back_footer) # Correctly aligned at the bottom

    draw_back = ImageDraw.Draw(back_card)

    # Address English (Left side)
    eng_addr_lines = textwrap.wrap(f"Address: {data.get('address', '')}", width=40)
    y_text = 150
    for line in eng_addr_lines:
        draw_back.text((40, y_text), line, font=font_eng_reg, fill="black")
        y_text += 30

    # Address Marathi (Right side) - using KF-Kiran font
    mar_addr_lines = textwrap.wrap(f"पत्ता: {data.get('address_mr', '')}", width=35)
    y_text = 150
    for line in mar_addr_lines:
        draw_back.text((520, y_text), line, font=font_marathi, fill="black")
        y_text += 35
        
    # Aadhaar Number on back
    draw_back.text((360, 485), data.get('aadhaar_no', ''), font=font_aadhaar, fill="black")
    
    back_card.save("id_card_back.png")
    
    return "id_card_front.png", "id_card_back.png"

# ==============================================================================
# 3. PRINTER LOGIC (Unchanged)
# ==============================================================================
def print_image(image_path, printer_name=None):
    system = platform.system()
    if not os.path.exists(image_path):
        messagebox.showerror("Error", f"Image path '{image_path}' not found.")
        return
    command = ""
    if system == "Windows":
        command = f'mspaint /pt "{image_path}"'
        if printer_name: command = f'mspaint /pt "{image_path}" "{printer_name}"'
    elif system in ["Linux", "Darwin"]:
        lpr_cmd = "lpr" if system == "Darwin" else "lp"
        printer_arg = f'-P "{printer_name}"' if system == "Darwin" else f'-d "{printer_name}"'
        command = f'{lpr_cmd} {printer_arg if printer_name else ""} "{image_path}"'
    else:
        messagebox.showerror("Unsupported OS", "Your OS is not supported for direct printing.")
        return
    try: os.system(command)
    except Exception as e: messagebox.showerror("Printing Failed", f"Failed to send print job: {e}")

# ==============================================================================
# 4. GUI APPLICATION CLASS (Unchanged)
# ==============================================================================
class IDCardApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ID Card Studio (Manual Photo Upload)")
        self.geometry("900x650")
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
        
        self.select_button = ttk.Button(control_frame, text="2. Select PDF & Generate", command=self.select_and_process_pdf)
        self.select_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.print_button = ttk.Button(control_frame, text="3. Print ID Card", command=self.print_card_action, state="disabled")
        self.print_button.pack(side=tk.LEFT, padx=5, pady=5)

        status_frame = ttk.Frame(self, padding="0 10 10 10")
        status_frame.pack(fill=tk.X, side=tk.TOP)
        self.status_label = ttk.Label(status_frame, text="Please upload a photo to begin.")
        self.status_label.pack(side=tk.LEFT)
        
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
            self.status_label.config(text="Photo selected. Now select the PDF.")

    def select_and_process_pdf(self):
        if not self.photo_path:
            messagebox.showerror("Error", "Please upload a photo first using the 'Upload Photo' button.")
            return

        self.pdf_path = filedialog.askopenfilename(title="Select PDF", filetypes=(("PDF Files", "*.pdf"),))
        if not self.pdf_path: return
        
        password = "VARA2004" # Your hardcoded password
        # password = self.password_entry.get() # Uncomment to use the password field
        
        self.status_label.config(text=f"Processing: {os.path.basename(self.pdf_path)}...")
        self.update_idletasks()
        try:
            data = extract_data_from_pdf(self.pdf_path, password)
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
        printer_name = "Epson L805 Series" # <-- IMPORTANT: Change this to your printer's name
        if not self.front_image_path or not self.back_image_path:
            messagebox.showwarning("Warning", "No card images to print.")
            return
        if messagebox.askokcancel("Print Front", f"Ready to print the FRONT to '{printer_name}'?"):
            print_image(self.front_image_path, printer_name)
        if messagebox.askokcancel("Print Back", "Flip the card in the tray.\nClick OK to print the BACK."):
            print_image(self.back_image_path, printer_name)
        self.status_label.config(text="Print jobs sent.")

# ==============================================================================
# 5. SCRIPT EXECUTION
# ==============================================================================
if __name__ == "__main__":
    app = IDCardApp()
    app.mainloop()
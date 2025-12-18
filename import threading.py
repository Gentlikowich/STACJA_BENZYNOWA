import threading
import time
import random
import tkinter as tk
from tkinter import ttk, scrolledtext
import queue

class SymulacjaStacjiBenzynowej:
    def __init__(self, root):
        self.root = root
        self.root.title("System Monitorowania Stacji Paliw - Wielowątkowość")
        self.root.geometry("950x800")
        self.root.configure(bg="#f4f7f6")
        
        # --- Parametry Systemu ---
        self.limit_zbiornika = 500
        self.zbiorniki = {"Benzyna": 200, "Diesel": 200, "LPG": 150}
        self.obsluzone_auta = 0
        self.godzina = 8
        self.cysterna_w_drodze = False
        
        # --- Synchronizacja i Komunikacja Międzywątkowa ---
        self.blokada_zbiornikow = threading.Lock() # Mutex dla zasobów paliwa
        self.blokada_kasy = threading.Lock()       # Mutex dla punktu płatności
        self.blokada_stats = threading.Lock()      # Mutex dla licznika aut
        self.kolejka_pojazdow = queue.Queue()      # Bezpieczna kolejka FIFO
        
        # Definicja dystrybutorów z kolorami UI
        self.dystrybutory = {
            "Dystrybutor 1 (B)": {"lock": threading.Lock(), "typ": "Benzyna", "id": 0, "color": "#1e88e5"},
            "Dystrybutor 2 (D)": {"lock": threading.Lock(), "typ": "Diesel", "id": 1, "color": "#43a047"},
            "Dystrybutor 3 (U)": {"lock": threading.Lock(), "typ": "Uniwersalny", "id": 2, "color": "#fb8c00"},
        }

        self.setup_styles()
        self.buduj_interfejs()

        # --- Uruchomienie Silnika Symulacji ---
        threading.Thread(target=self.watek_czasu, daemon=True).start()
        threading.Thread(target=self.watek_generatora_aut, daemon=True).start()
        threading.Thread(target=self.watek_menedzera_kolejki, daemon=True).start()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Vertical.TProgressbar", background="#26c6da", thickness=35)
        style.configure("TProgressbar", thickness=15)

    def buduj_interfejs(self):
        # --- NAGŁÓWEK ---
        header = tk.Frame(self.root, bg="#263238", height=70)
        header.pack(fill="x")
        
        self.lbl_zegar = tk.Label(header, text="🕒 08:00", font=("Segoe UI", 16, "bold"), bg="#263238", fg="white")
        self.lbl_zegar.pack(side=tk.LEFT, padx=25)
        
        title = tk.Label(header, text="CENTRALNY SYSTEM MONITOROWANIA PALIW", font=("Segoe UI", 12, "bold"), bg="#263238", fg="#90a4ae")
        title.pack(side=tk.LEFT, padx=40)
        
        self.lbl_stats = tk.Label(header, text="Obsłużone: 0", font=("Segoe UI", 12, "bold"), bg="#263238", fg="#ffeb3b")
        self.lbl_stats.pack(side=tk.RIGHT, padx=25)

        # --- GŁÓWNY OBSZAR ROBOCZY ---
        container = tk.Frame(self.root, bg="#f4f7f6")
        container.pack(fill="both", expand=True, padx=15, pady=15)

        # LEWO: Zbiorniki (Wizualizacja Zasobów)
        z_frame = tk.LabelFrame(container, text=" POZIOMY W ZBIORNIKACH ", bg="white", font=("Arial", 10, "bold"), padx=15, pady=15)
        z_frame.pack(side=tk.LEFT, fill="y", padx=10)

        self.tank_bars = {}
        self.tank_labels = {}
        for p in self.zbiorniki.keys():
            f = tk.Frame(z_frame, bg="white")
            f.pack(side=tk.LEFT, padx=10)
            
            pb = ttk.Progressbar(f, orient="vertical", length=220, mode="determinate", style="Vertical.TProgressbar")
            pb.pack()
            self.tank_bars[p] = pb
            
            l = tk.Label(f, text=f"{p}\n{self.zbiorniki[p]}L", font=("Arial", 9, "bold"), bg="white", pady=10)
            l.pack()
            self.tank_labels[p] = l

        # PRAWO: Dystrybutory i Logi
        p_frame = tk.Frame(container, bg="#f4f7f6")
        p_frame.pack(side=tk.LEFT, fill="both", expand=True)

        # Karty Dystrybutorów
        d_container = tk.Frame(p_frame, bg="#f4f7f6")
        d_container.pack(fill="x")

        self.status_labels = []
        self.progress_bars = []
        for name, info in self.dystrybutory.items():
            card = tk.Frame(d_container, bg="white", relief=tk.RIDGE, bd=1)
            card.pack(side=tk.LEFT, padx=10, pady=5, fill="both", expand=True)
            
            tk.Label(card, text=name, bg=info["color"], fg="white", font=("Arial", 10, "bold"), pady=8).pack(fill="x")
            
            st_lbl = tk.Label(card, text="WOLNY", fg="#4caf50", bg="white", font=("Arial", 10, "bold"), pady=15)
            st_lbl.pack()
            self.status_labels.append(st_lbl)
            
            pb = ttk.Progressbar(card, orient="horizontal", length=140, mode="determinate")
            pb.pack(padx=20, pady=10)
            self.progress_bars.append(pb)

        # Panel Sterowania i Logi
        ctrl_frame = tk.Frame(p_frame, bg="#f4f7f6")
        ctrl_frame.pack(fill="both", expand=True, pady=20)

        self.btn_manual = tk.Button(ctrl_frame, text="🚚 WEZWIJ CYSTERNĘ (TRYB RĘCZNY)", command=self.manualny_wywolanie, 
                                   bg="#e53935", fg="white", font=("Arial", 10, "bold"), pady=10, relief=tk.FLAT)
        self.btn_manual.pack(fill="x", padx=10, pady=5)

        self.log_area = scrolledtext.ScrolledText(ctrl_frame, height=15, font=("Consolas", 9), bg="#1e282c", fg="#b8c7ce")
        self.log_area.pack(fill="both", expand=True, padx=10, pady=10)

    # --- LOGIKA OPERACYJNA ---

    def log(self, msg):
        self.log_area.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_area.see(tk.END)

    def aktualizuj_ui_zbiornikow(self):
        def refresh():
            for p, val in self.zbiorniki.items():
                self.tank_bars[p]['value'] = (val / self.limit_zbiornika) * 100
                self.tank_labels[p].config(text=f"{p}\n{val}L", fg="#e53935" if val < 50 else "black")
        self.root.after(0, refresh)

    def manualny_wywolanie(self):
        if not self.cysterna_w_drodze:
            threading.Thread(target=self.proces_cysterny, daemon=True).start()

    def proces_cysterny(self):
        """Wątek Producenta Zasobów"""
        self.cysterna_w_drodze = True
        self.log("🚛 CYSTERNA: Wyjazd z bazy do stacji (opóźnienie 6s)...")
        time.sleep(6) # Symulacja drogi
        with self.blokada_zbiornikow:
            for p in self.zbiorniki: self.zbiorniki[p] = self.limit_zbiornika
            self.log("🚛 CYSTERNA: Dotarto na miejsce. Wszystkie zbiorniki pełne (500L).")
            self.cysterna_w_drodze = False
        self.aktualizuj_ui_zbiornikow()

    def watek_czasu(self):
        while True:
            time.sleep(8) # 8 sekund = 1 godzina symulacji
            self.godzina = (self.godzina + 1) % 24
            self.root.after(0, lambda: self.lbl_zegar.config(text=f"🕒 {self.godzina:02d}:00"))

    def watek_generatora_aut(self):
        auto_id = 1
        while True:
            # Natężenie ruchu zależne od godziny (Dzień: 2-4s, Noc: 7-12s)
            wait = random.uniform(2, 4) if 7 <= self.godzina < 22 else random.uniform(7, 12)
            time.sleep(wait)
            self.kolejka_pojazdow.put({"id": auto_id, "typ": random.choice(["Benzyna", "Diesel", "LPG"])})
            auto_id += 1

    def watek_menedzera_kolejki(self):
        """Wątek Dyspozytora - zarządza kolejką i wywołuje cysternę"""
        while True:
            auto = self.kolejka_pojazdow.get()
            przypisano = False
            while not przypisano:
                with self.blokada_zbiornikow:
                    # Automatyczne wezwanie przy poziomie < 70L
                    if self.zbiorniki[auto["typ"]] < 70 and not self.cysterna_w_drodze:
                        self.log(f"🚨 ALERT: Mało {auto['typ']}! System wzywa cysternę.")
                        threading.Thread(target=self.proces_cysterny, daemon=True).start()
                    
                    # Czekaj jeśli krytycznie mało (< 15L)
                    if self.zbiorniki[auto["typ"]] < 15:
                        time.sleep(2)
                        continue

                # Szukanie wolnego dystrybutora
                for name, info in self.dystrybutory.items():
                    if (info["typ"] == auto["typ"] or info["typ"] == "Uniwersalny") and not info["lock"].locked():
                        threading.Thread(target=self.obsluga_tankowania, args=(auto, info), daemon=True).start()
                        przypisano = True
                        break
                if not przypisano: time.sleep(0.5)

    def obsluga_tankowania(self, auto, info):
        """Wątek obsługi konkretnego klienta"""
        idx = info["id"]
        ile_paliwa = random.randint(35, 85)
        
        with info["lock"]:
            with self.blokada_zbiornikow:
                zatankowano = min(ile_paliwa, self.zbiorniki[auto["typ"]])
                self.zbiorniki[auto["typ"]] -= zatankowano
            
            self.aktualizuj_ui_zbiornikow()
            self.root.after(0, lambda: self.status_labels[idx].config(text=f"TANKOWANIE\nAuto {auto['id']} ({auto['typ']})", fg="#ef6c00"))
            
            # Symulacja procesu tankowania
            czas = zatankowano / 12
            for i in range(101):
                time.sleep(czas / 100)
                self.root.after(0, lambda v=i: self.progress_bars[idx].configure(value=v))
            
            self.log(f"⛽ Auto {auto['id']} zakończyło tankowanie {zatankowano}L {auto['typ']}.")
            self.root.after(0, lambda: self.status_labels[idx].config(text="WOLNY", fg="#4caf50"))
            self.root.after(0, lambda: self.progress_bars[idx].configure(value=0))

        # Sekcja płatności
        with self.blokada_kasy:
            time.sleep(1.2)
            with self.blokada_stats:
                self.obsluzone_auta += 1
                self.root.after(0, lambda: self.lbl_stats.config(text=f"Obsłużone: {self.obsluzone_auta}"))
            self.log(f"💰 Auto {auto['id']} zapłaciło i odjechało.")

if __name__ == "__main__":
    root = tk.Tk()
    app = SymulacjaStacjiBenzynowej(root)
    root.mainloop()
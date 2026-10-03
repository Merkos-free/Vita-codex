"""Graphical local companion; no work begins until the owner presses a button."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from .companion import Companion, export_public_bundle

BG = '#080c12'
PANEL = '#111923'
TEXT = '#edf3f9'
MUTED = '#9cadbf'
ACCENT = '#16baf5'


class Window:
    def __init__(self, root: tk.Tk, controller: Companion | None = None):
        self.root, self.controller = root, controller or Companion()
        self.closed = False
        self.closing = False
        self.timer = None
        self.exporting = False
        self.export_result = None
        self.root.title('Codex Vita — Bridge для компьютера (тестовая версия)')
        self.root.geometry('1000x750')
        self.root.minsize(960, 720)
        self.root.configure(bg=BG)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame', background=BG)
        style.configure('Card.TFrame', background=PANEL)
        style.configure('TLabel', background=BG, foreground=TEXT, font=('Segoe UI', 11))
        style.configure('Muted.TLabel', foreground=MUTED, font=('Segoe UI', 10))
        style.configure('Card.TLabel', background=PANEL)
        style.configure('TEntry', fieldbackground='#243447', foreground=TEXT, insertcolor=TEXT, padding=7)
        style.configure('TButton', background='#243447', foreground=TEXT, padding=(12, 9), font=('Segoe UI', 10))
        style.map('TButton', background=[('active', '#34516a')], foreground=[('disabled', '#657583')])
        style.configure('Accent.TButton', background=ACCENT, foreground=BG)
        style.map('Accent.TButton', background=[('active', '#59d7ff')], foreground=[('disabled', '#657583')])
        self.host = tk.StringVar(value='')
        self.project = tk.StringVar(value='')
        self.codex = tk.StringVar(value='codex')
        default_parent = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'CodexVita'
        self.output = tk.StringVar(value=str(default_parent / 'setup-1'))
        self.config = tk.StringVar(value='')
        self.status = tk.StringVar(value='ВЫКЛЮЧЕНО')
        self.message = tk.StringVar(value='Выберите отдельную тестовую папку. Никакие процессы пока не запущены.')
        self.endpoint = tk.StringVar(value='Адрес не подготовлен')
        self.pin = tk.StringVar(value='— — — — — —')
        self.expiry = tk.StringVar(value='Код появится после проверки входа в Codex.')
        self.widgets = []
        head = ttk.Frame(root, padding=(28, 22, 28, 10)); head.pack(fill='x')
        ttk.Label(head, text='< >  CODEX VITA', font=('Segoe UI', 23, 'bold')).pack(anchor='w')
        ttk.Label(head, text='Локальный Bridge • ChatGPT-вход остаётся на компьютере • Без отдельного API',
                  style='Muted.TLabel').pack(anchor='w', pady=(6, 0))
        ttk.Label(head, text='ТЕСТОВЫЙ КАНДИДАТ   ·   READ-ONLY   ·   ДИКТОВКА НЕ ПОДКЛЮЧЕНА',
                  foreground=ACCENT, font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=10)
        body = ttk.Frame(root, padding=(28, 0)); body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=3); body.columnconfigure(1, weight=2)
        left = ttk.Frame(body, style='Card.TFrame', padding=18); left.grid(row=0, column=0, sticky='nsew', padx=(0, 16))
        right = ttk.Frame(body, style='Card.TFrame', padding=18); right.grid(row=0, column=1, sticky='nsew')
        left.columnconfigure(0, weight=1)
        ttk.Label(left, text='1. Подготовка компьютера', style='Card.TLabel', font=('Segoe UI', 15, 'bold')).grid(row=0, column=0, sticky='w', pady=(0, 12))
        fields = [('IPv4 компьютера в домашней сети', self.host, None),
                  ('Отдельная тестовая папка проекта', self.project, self.choose_project),
                  ('Официальный Codex (имя или путь)', self.codex, self.choose_codex),
                  ('Новая папка настроек — ВНЕ проекта', self.output, self.choose_output)]
        for i, (title, variable, browse) in enumerate(fields):
            row = i * 3 + 1
            ttk.Label(left, text=title, style='Card.TLabel', font=('Segoe UI', 10)).grid(row=row, column=0, sticky='w')
            field = ttk.Frame(left, style='Card.TFrame'); field.grid(row=row+1, column=0, sticky='ew', pady=(4, 12)); field.columnconfigure(0, weight=1)
            entry = ttk.Entry(field, textvariable=variable, width=37); entry.grid(row=0, column=0, sticky='ew'); self.widgets.append(entry)
            if browse:
                button = ttk.Button(field, text='…', width=3, command=browse); button.grid(row=0, column=1, padx=(5, 0)); self.widgets.append(button)
        self.prepare_button = ttk.Button(left, text='Подготовить настройки', style='Accent.TButton', command=self.prepare)
        self.prepare_button.grid(row=13, column=0, sticky='ew', pady=(2, 8)); self.widgets.append(self.prepare_button)
        ttk.Label(left, text='Нужны установленный Codex и OpenSSL.\nСертификат действует 30 дней. Firewall не меняется.',
                  style='Card.TLabel', foreground=MUTED, font=('Segoe UI', 9)).grid(row=14, column=0, sticky='w')
        ttk.Label(right, text='2. Подключение Vita', style='Card.TLabel', font=('Segoe UI', 15, 'bold')).pack(anchor='w')
        ttk.Label(right, textvariable=self.status, style='Card.TLabel', foreground=ACCENT,
                  font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(18, 12))
        ttk.Label(right, textvariable=self.endpoint, style='Card.TLabel', wraplength=310).pack(anchor='w')
        ttk.Label(right, textvariable=self.pin, style='Card.TLabel', font=('Consolas', 29, 'bold'),
                  foreground=ACCENT).pack(anchor='w', pady=(26, 8))
        ttk.Label(right, textvariable=self.expiry, style='Card.TLabel', wraplength=305,
                  foreground=MUTED).pack(anchor='w')
        ttk.Label(right, text='На Vita переносится только публичный\nкомплект: CA, адрес и отпечаток.\n\nНикогда не переносите server-key.pem\nи не вводите API-ключи в приставку.',
                  style='Card.TLabel', foreground=MUTED, font=('Segoe UI', 10)).pack(anchor='w', pady=24)
        self.export_button = ttk.Button(right, text='Сохранить комплект для Vita…', command=self.export)
        self.export_button.pack(fill='x', side='bottom', pady=(12, 0))
        bottom = ttk.Frame(root, padding=(28, 14, 28, 18)); bottom.pack(fill='x')
        bottom.columnconfigure(1, weight=1)
        self.load_button = ttk.Button(bottom, text='Открыть config.json…', command=self.load); self.load_button.grid(row=0, column=0, padx=(0, 10))
        entry = ttk.Entry(bottom, textvariable=self.config); entry.grid(row=0, column=1, sticky='ew'); self.widgets.append(entry)
        self.start_button = ttk.Button(bottom, text='Запустить', style='Accent.TButton', command=self.start)
        self.start_button.grid(row=0, column=2, padx=10)
        self.stop_button = ttk.Button(bottom, text='Остановить', command=self.controller.stop); self.stop_button.grid(row=0, column=3)
        ttk.Label(bottom, textvariable=self.message, wraplength=930, style='Muted.TLabel').grid(row=1, column=0, columnspan=4, sticky='w', pady=(12, 0))
        ttk.Label(bottom, text='Остановка отзывает подключение, но не откатывает файлы и не гарантирует завершение фоновых команд.',
                  style='Muted.TLabel', wraplength=930).grid(row=2, column=0, columnspan=4, sticky='w', pady=(8, 0))
        self.poll()

    def choose_project(self):
        value = filedialog.askdirectory(parent=self.root, title='Выберите отдельный тестовый проект')
        if value: self.project.set(value)

    def choose_codex(self):
        value = filedialog.askopenfilename(parent=self.root, title='Официальный Codex')
        if value: self.codex.set(value)

    def choose_output(self):
        value = filedialog.askdirectory(parent=self.root, title='Родительская личная папка вне проекта')
        if value: self.output.set(str(Path(value) / 'codex-vita-setup'))

    def prepare(self):
        if not self.host.get().strip() or not self.project.get().strip() or not self.output.get().strip():
            messagebox.showerror('Не заполнены поля', 'Укажите IP, тестовый проект и новую папку настроек.', parent=self.root)
            return
        self.controller.prepare(self.host.get().strip(), Path(self.project.get()), Path(self.output.get()), self.codex.get().strip())

    def load(self):
        value = filedialog.askopenfilename(parent=self.root, title='Открыть локальный config.json', filetypes=[('JSON', '*.json')])
        if value: self.config.set(value)

    def start(self):
        if self.config.get().strip(): self.controller.start(Path(self.config.get()))

    def export(self):
        if not self.config.get() or self.controller.busy or self.exporting: return
        value = filedialog.asksaveasfilename(parent=self.root, title='Новый публичный ZIP (существующий не перезаписывается)',
                                           initialfile='vita-public-connection.zip', defaultextension='.zip', filetypes=[('ZIP', '*.zip')])
        if not value: return
        config, destination = Path(self.config.get()), Path(value)
        self.exporting = True; self.export_result = None
        def work():
            try:
                export_public_bundle(config, destination)
                self.export_result = 'Готово: публичные файлы из ZIP позже переносятся в ux0:data/vita-codex/.'
            except Exception:
                self.export_result = 'Экспорт отклонён. Проверьте конфигурацию, сертификат и новое имя ZIP.'
        threading.Thread(target=work, name='vita-public-export', daemon=True).start()

    def poll(self):
        if self.closed: return
        state = self.controller.snapshot()
        busy = self.controller.busy or self.exporting or self.closing
        for widget in self.widgets + [self.load_button]: widget.configure(state='disabled' if busy else 'normal')
        self.start_button.configure(state='normal' if not busy and self.config.get() else 'disabled')
        self.stop_button.configure(state='normal' if self.controller.busy else 'disabled')
        self.export_button.configure(state='normal' if not busy and self.config.get() else 'disabled')
        names = {'idle':'ВЫКЛЮЧЕНО', 'preparing':'ПОДГОТОВКА', 'prepared':'НАСТРОЙКИ ГОТОВЫ', 'starting':'ПРОВЕРКА CODEX',
                 'running':'BRIDGE ЗАПУЩЕН', 'stopping':'ОСТАНОВКА', 'stopped':'ВЫКЛЮЧЕНО', 'error':'НЕ ПОДКЛЮЧЕНО'}
        self.status.set(names[state.phase]); self.message.set(state.message)
        if state.config and state.phase in ('prepared', 'running'): self.config.set(state.config)
        if state.endpoint: self.endpoint.set(state.endpoint)
        self.pin.set(state.pin or '— — — — — —')
        self.expiry.set(f'Код действует ещё {state.seconds} с.' if state.pin else
                        ('Vita сопряжена. Токен не отображается.' if state.paired else 'Для нового кода остановите и запустите Bridge.'))
        if self.exporting and self.export_result is not None:
            self.exporting = False
            messagebox.showinfo('Публичный комплект', self.export_result, parent=self.root)
        if self.closing and not self.controller.busy and not self.exporting:
            self.destroy(); return
        self.timer = self.root.after(100, self.poll)

    def close(self):
        if self.controller.busy or self.exporting:
            if not messagebox.askyesno('Завершить?', 'Остановить Bridge и отозвать подключение Vita? Это не откат файлов.', parent=self.root): return
            self.closing = True; self.controller.stop()
        else: self.destroy()

    def destroy(self):
        self.closed = True
        if self.timer: self.root.after_cancel(self.timer)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke-test', type=Path, help='CI only: open real Tk window, write state/geometry and exit; no connection')
    args = parser.parse_args()
    root = tk.Tk(); window = Window(root)
    if args.smoke_test:
        def smoke():
            root.update_idletasks()
            report = {'guiCreated': True, 'runtimeStarted': window.controller.busy,
                      'phase': window.controller.snapshot().phase, 'size': [root.winfo_width(), root.winfo_height()],
                      'voiceEnabled': False, 'platform': os.name}
            args.smoke_test.parent.mkdir(parents=True, exist_ok=True)
            args.smoke_test.write_text(json.dumps(report, indent=2), encoding='utf-8')
            window.destroy()
        root.after(500, smoke)
    root.mainloop()

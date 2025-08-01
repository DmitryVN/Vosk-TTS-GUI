import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from vosk_tts import Model, Synth
import os
import tempfile
import pygame  # Для воспроизведения
from threading import Thread  # Для асинхронного синтеза
from pydub import AudioSegment  # Для пост-обработки (скорость, паузы, MP3)
import time  # Для задержек
import re  # Для разбиения текста и поиска чисел
from num2words import num2words  # Для преобразования чисел в слова
import unicodedata  # Для нормализации символов
import string  # Для printable символов
import traceback  # Для полного лога ошибок
import datetime  # Для timestamp в логах

class TTSApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Vosk TTS Синтезатор")
        self.root.geometry("930x635")

        # Модель и синтезатор
        try:
            self.model = Model(model_name="vosk-model-tts-ru-0.9-multi")
            self.synth = Synth(self.model)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить модель: {e}")
            root.quit()

        # Пользовательский словарь (загружаем из дефолтного файла)
        self.dict_file = "pronunciation_dict.txt"
        self.pronunciation_dict = self.load_dictionary(self.dict_file)

        # Инициализация pygame
        pygame.mixer.init()

        # История файлов
        self.history = []

        # GUI элементы
        self.create_widgets()

        # Переменные
        self.playing = False
        self.temp_file = None
        self.max_speed = 2.0  # Максимальное ускорение для обычного текста
        self.max_speed_srt = 1.4  # Максимальное ускорение для SRT

    def create_widgets(self):
        # Текстовое поле с прокруткой
        self.text_label = tk.Label(self.root, text="Введите текст или используйте SRT ( <pause> для пауз, \n для абзацев):")
        self.text_label.pack()

        text_frame = tk.Frame(self.root)
        text_frame.pack()

        self.text_area = tk.Text(text_frame, height=10, width=70, undo=True)
        self.text_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(text_frame, command=self.text_area.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_area.config(yscrollcommand=scrollbar.set)

        # Контекстное меню
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Вырезать", command=self.cut_text)
        self.context_menu.add_command(label="Копировать", command=self.copy_text)
        self.context_menu.add_command(label="Вставить", command=self.paste_text)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Выделить всё", command=self.select_all)
        self.text_area.bind("<Button-3>", self.show_context_menu)

        # Выбор чтеца (0-56, всего 57)
        self.speaker_label = tk.Label(self.root, text="Чтец (speaker_id, 0-56):")
        self.speaker_label.pack()
        self.speaker_var = tk.IntVar(value=2)
        self.speaker_menu = ttk.Combobox(self.root, textvariable=self.speaker_var, values=list(range(57)))
        self.speaker_menu.pack()

        # Скорость (коэффициент, 0.5-2.0)
        self.speed_label = tk.Label(self.root, text="Скорость (0.5x - 2.0x):")
        self.speed_label.pack()
        self.speed_var = tk.DoubleVar(value=1.0)
        self.speed_slider = tk.Scale(self.root, from_=0.5, to=2.0, resolution=0.1, orient=tk.HORIZONTAL, variable=self.speed_var)
        self.speed_slider.pack()

        # Громкость
        self.volume_label = tk.Label(self.root, text="Громкость (0-100%):")
        self.volume_label.pack()
        self.volume_var = tk.IntVar(value=100)
        self.volume_slider = tk.Scale(self.root, from_=0, to=100, orient=tk.HORIZONTAL, variable=self.volume_var)
        self.volume_slider.pack()

        # Кнопки
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)

        self.synth_play_btn = tk.Button(button_frame, text="Синтезировать и проиграть", command=self.synth_and_play)
        self.synth_play_btn.pack(side=tk.LEFT, padx=5)

        self.synth_save_btn = tk.Button(button_frame, text="Синтезировать и сохранить", command=self.synth_and_save)
        self.synth_save_btn.pack(side=tk.LEFT, padx=5)

        self.srt_btn = tk.Button(button_frame, text="Синтезировать из SRT", command=self.synth_from_srt)
        self.srt_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = tk.Button(button_frame, text="Стоп", command=self.stop_playback)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        self.clear_btn = tk.Button(button_frame, text="Очистить текст", command=self.clear_text)
        self.clear_btn.pack(side=tk.LEFT, padx=5)

        self.dict_btn = tk.Button(button_frame, text="Редактировать словарь", command=self.edit_dictionary)
        self.dict_btn.pack(side=tk.LEFT, padx=5)

        self.about_btn = tk.Button(button_frame, text="О программе", command=self.show_about)
        self.about_btn.pack(side=tk.LEFT, padx=5)

        # История
        self.history_label = tk.Label(self.root, text="История файлов:")
        self.history_label.pack()
        self.history_list = tk.Listbox(self.root, height=5, width=70)
        self.history_list.pack()
        self.history_list.bind("<Double-Button-1>", self.open_history_file)

        # Прогресс
        self.progress = ttk.Progressbar(self.root, orient="horizontal", length=400, mode="determinate", maximum=100)
        self.progress.pack(pady=10)

    def show_context_menu(self, event):
        self.context_menu.post(event.x_root, event.y_root)

    def cut_text(self):
        self.text_area.event_generate("<<Cut>>")

    def copy_text(self):
        self.text_area.event_generate("<<Copy>>")

    def paste_text(self):
        self.text_area.event_generate("<<Paste>>")

    def select_all(self):
        self.text_area.tag_add("sel", "1.0", "end")

    def clear_text(self):
        self.text_area.delete("1.0", tk.END)

    def show_about(self):
        messagebox.showinfo("О программе", "Vosk TTS Синтезатор\nВерсия 1.0\nИспользует vosk-tts для русского TTS.\nАвтор: DmitryVN\nhttps://github.com/DmitryVN/Vosk-TTS-GUI")

    def load_dictionary(self, file_path):
        try:
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    return {line.split(":", 1)[0].strip(): line.split(":", 1)[1].strip() for line in lines if ":" in line}
            return {}
        except Exception as e:
            messagebox.showwarning("Ошибка", f"Не удалось загрузить словарь: {e}")
            return {}

    def save_dictionary(self, file_path, dictionary):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                for k, v in dictionary.items():
                    f.write(f"{k}: {v}\n")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить словарь: {e}")

    def edit_dictionary(self):
        dict_window = tk.Toplevel(self.root)
        dict_window.title("Редактировать словарь произношения")
        dict_window.geometry("400x300")

        text_area = tk.Text(dict_window, height=15, width=50)
        text_area.pack()

        dict_text = "\n".join([f"{k}: {v}" for k, v in self.pronunciation_dict.items()])
        text_area.insert(tk.END, dict_text)

        button_frame = tk.Frame(dict_window)
        button_frame.pack(pady=5)

        def load_from_file():
            file = filedialog.askopenfilename(filetypes=[("Text files", "*.txt *.dic")])
            if file:
                new_dict = self.load_dictionary(file)
                if new_dict:
                    self.pronunciation_dict.update(new_dict)
                    text_area.delete("1.0", tk.END)
                    text_area.insert(tk.END, "\n".join([f"{k}: {v}" for k, v in self.pronunciation_dict.items()]))
                    messagebox.showinfo("Успех", "Словарь загружен из файла!")

        def save_to_file():
            file = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt *.dic")])
            if file:
                temp_dict = {}
                lines = text_area.get("1.0", tk.END).strip().split("\n")
                for line in lines:
                    if ":" in line:
                        key, value = line.split(":", 1)
                        temp_dict[key.strip()] = value.strip()
                self.save_dictionary(file, temp_dict)
                messagebox.showinfo("Успех", "Словарь сохранён в файл!")

        def save_dict():
            new_dict = {}
            lines = text_area.get("1.0", tk.END).strip().split("\n")
            for line in lines:
                if ":" in line:
                    try:
                        key, value = line.split(":", 1)
                        new_dict[key.strip()] = value.strip()
                    except:
                        pass
            self.pronunciation_dict = new_dict
            self.save_dictionary(self.dict_file, new_dict)  # Сохраняем в дефолтный
            messagebox.showinfo("Успех", "Словарь обновлён!")
            dict_window.destroy()

        load_btn = tk.Button(button_frame, text="Загрузить из файла", command=load_from_file)
        load_btn.pack(side=tk.LEFT, padx=5)

        save_file_btn = tk.Button(button_frame, text="Сохранить в файл", command=save_to_file)
        save_file_btn.pack(side=tk.LEFT, padx=5)

        save_btn = tk.Button(button_frame, text="Сохранить изменения", command=save_dict)
        save_btn.pack(side=tk.LEFT, padx=5)

    def apply_dictionary_and_numbers(self, text):
        # Расширенная очистка: нормализация, удаление не-printable, скобок, замена тире/кавычек
        text = unicodedata.normalize('NFKC', text)
        text = ''.join(c for c in text if c in string.printable or unicodedata.category(c) != 'Cc')
        text = re.sub(r'[```math```{}KATEX_INLINE_OPENKATEX_INLINE_CLOSE]', '', text)  # Удаление скобок
        text = text.replace('–', '-').replace('—', '-').replace('−', '-')  # Замена тире на дефис
        text = text.replace('«', '"').replace('»', '"').replace('‘', "'").replace('’', "'").replace('"', ' ').replace("'", ' ')  # Кавычки на пробел
        text = text.replace('…', '...')  # Ellipsis
        text = text.replace('ё', 'е')
        text = re.sub(r'[\r\n]+', ' ', text)
        # Базовая транслитерация латинского/английского текста
        text = self.transliterate_latin(text)
        # Преобразование чисел
        text = self.convert_numbers_to_words(text)
        # Словарь
        for key, value in self.pronunciation_dict.items():
            text = text.replace(key, value)
        return text

    def transliterate_latin(self, text):
        translit_map = {
            'a': 'а', 'b': 'б', 'c': 'к', 'd': 'д', 'e': 'е', 'f': 'ф', 'g': 'г', 'h': 'х', 'i': 'и', 'j': 'й',
            'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н', 'o': 'о', 'p': 'п', 'q': 'к', 'r': 'р', 's': 'с', 't': 'т',
            'u': 'у', 'v': 'в', 'w': 'в', 'x': 'кс', 'y': 'й', 'z': 'з',
            'A': 'А', 'B': 'Б', 'C': 'К', 'D': 'Д', 'E': 'Е', 'F': 'Ф', 'G': 'Г', 'H': 'Х', 'I': 'И', 'J': 'Й',
            'K': 'К', 'L': 'Л', 'M': 'М', 'N': 'Н', 'O': 'О', 'P': 'П', 'Q': 'К', 'R': 'Р', 'S': 'С', 'T': 'Т',
            'U': 'У', 'V': 'В', 'W': 'В', 'X': 'Кс', 'Y': 'Й', 'Z': 'З'
        }
        def replace_latin(match):
            return ''.join(translit_map.get(c, c) for c in match.group(0))
        text = re.sub(r'[a-zA-Z]+', replace_latin, text)
        return text

    def convert_numbers_to_words(self, text):
        # Дроби (1/2 -> одна вторая)
        text = re.sub(r'(\d+)/(\d+)', lambda m: f"{num2words(int(m.group(1)), lang='ru')} {num2words(int(m.group(2)), lang='ru', to='ordinal')}", text)
        # Проценты (50% или 50 % -> пятьдесят процентов)
        text = re.sub(r'(\d+)\s*%', lambda m: f"{num2words(int(m.group(1)), lang='ru')} процентов", text)
        # Десятичные с точкой или запятой (3.14 или 1,9 -> три целых четырнадцать сотых)
        text = re.sub(r'(\d+)[.,](\d+)', lambda m: f"{num2words(int(m.group(1)), lang='ru')} целых {num2words(int(m.group(2)), lang='ru')} {self.get_fraction_word(len(m.group(2)))}", text)
        # Простые числа (123 -> сто двадцать три)
        text = re.sub(r'\b(\d+)\b', lambda m: num2words(int(m.group(1)), lang='ru'), text)
        # Валюта (100 руб. -> сто рублей)
        text = re.sub(r'(\d+) руб\.', lambda m: f"{num2words(int(m.group(1)), lang='ru')} рублей", text)
        return text

    def get_fraction_word(self, digits):
        if digits == 1: return "десятых"
        elif digits == 2: return "сотых"
        elif digits == 3: return "тысячных"
        return "долей"

    def synth_text_to_wav(self, text, output_file, speaker_id, speed_factor=1.0):
        text = self.apply_dictionary_and_numbers(text)
        combined = AudioSegment.empty()
        pause_short = AudioSegment.silent(duration=500)  # Для <pause>
        pause_long = AudioSegment.silent(duration=1000)  # Для \n (абзацы)

        # Улучшенное разбиение
        try:
            parts = re.split(r'(?<=[\.\!\?\;])\s*|\n', text)
            if len(text) > 1000:
                chunks = []
                current_chunk = ""
                for part in parts:
                    if len(current_chunk) + len(part) > 500:
                        chunks.append(current_chunk.strip())
                        current_chunk = part
                    else:
                        current_chunk += part + " "
                if current_chunk:
                    chunks.append(current_chunk.strip())
            else:
                chunks = [p.strip() for p in parts if p.strip()]
        except:
            chunks = [text]

        for i, chunk in enumerate(chunks):
            chunk = chunk.replace("<pause>", "")
            if chunk:
                temp_out = tempfile.mktemp(suffix=".wav")
                self.synth.synth(chunk, temp_out, speaker_id=speaker_id)
                segment = AudioSegment.from_wav(temp_out)
                if speed_factor != 1.0:
                    segment = segment.speedup(playback_speed=speed_factor) if speed_factor > 1 else segment._spawn(segment.raw_data, overrides={"frame_rate": int(segment.frame_rate * speed_factor)})
                    segment = segment.set_frame_rate(22050)  # Стандартный rate
                combined += segment
                if "<pause>" in chunk:
                    combined += pause_short
                if "\n" in chunk or i < len(chunks) - 1:
                    combined += pause_long
                os.remove(temp_out)
        combined.export(output_file, format="wav")

    def synth_and_play(self):
        text = self.text_area.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Ошибка", "Введите текст!")
            return

        speaker_id = self.speaker_var.get()
        speed_factor = self.speed_var.get()
        volume = self.volume_var.get() / 100.0

        self.temp_file = tempfile.mktemp(suffix=".wav")

        self.progress["value"] = 0
        thread = Thread(target=self._synth_and_play_thread, args=(text, speaker_id, speed_factor, volume))
        thread.start()

    def _synth_and_play_thread(self, text, speaker_id, speed_factor, volume):
        try:
            self.synth_text_to_wav(text, self.temp_file, speaker_id, speed_factor)
            
            # Вычисляем длительность аудио
            audio = AudioSegment.from_wav(self.temp_file)
            duration = audio.duration_seconds
            
            pygame.mixer.music.load(self.temp_file)
            pygame.mixer.music.set_volume(volume)
            pygame.mixer.music.play()
            self.playing = True
            
            # Реальный прогресс
            start_time = time.time()
            while self.playing and pygame.mixer.music.get_busy():
                elapsed = (time.time() - start_time)
                progress_value = min(100, (elapsed / duration) * 100 if duration > 0 else 0)
                self.root.after(0, lambda v=progress_value: self.progress.__setitem__("value", v))
                time.sleep(0.1)
            
            self.playing = False
            time.sleep(0.5)  # Задержка для освобождения файла
            try:
                os.remove(self.temp_file)
            except OSError as e:
                print(f"Ошибка удаления temp файла: {e}")
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Ошибка", str(e)))
        finally:
            self.root.after(0, lambda: self.progress.__setitem__("value", 0))

    def synth_and_save(self):
        text = self.text_area.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Ошибка", "Введите текст!")
            return

        speaker_id = self.speaker_var.get()
        speed_factor = self.speed_var.get()

        filetypes = [("WAV files", "*.wav"), ("MP3 files", "*.mp3")]
        output_file = filedialog.asksaveasfilename(filetypes=filetypes, defaultextension=".wav")
        if not output_file:
            return

        format = "mp3" if output_file.endswith(".mp3") else "wav"

        self.progress["value"] = 0
        thread = Thread(target=self._synth_and_save_thread, args=(text, output_file, speaker_id, speed_factor, format))
        thread.start()

    def _synth_and_save_thread(self, text, output_file, speaker_id, speed_factor, format):
        try:
            temp_wav = tempfile.mktemp(suffix=".wav")
            self.synth_text_to_wav(text, temp_wav, speaker_id, speed_factor)
            audio = AudioSegment.from_wav(temp_wav)
            audio.export(output_file, format=format)
            os.remove(temp_wav)
            self.root.after(0, lambda f=output_file: self.add_to_history(f))
            self.root.after(0, lambda: messagebox.showinfo("Успех", f"Файл сохранён: {output_file}"))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Ошибка", str(e)))
        finally:
            self.root.after(0, lambda: self.progress.__setitem__("value", 0))

    def synth_from_srt(self):
        srt_file = filedialog.askopenfilename(filetypes=[("SRT files", "*.srt")])
        if not srt_file:
            return

        try:
            subtitles = self.parse_srt(srt_file)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Ошибка парсинга SRT: {e}")
            return

        if not subtitles:
            messagebox.showwarning("Ошибка", "SRT пустой или неверный формат!")
            return

        # Выбор файла для сохранения
        filetypes = [("WAV files", "*.wav"), ("MP3 files", "*.mp3")]
        output_file = filedialog.asksaveasfilename(filetypes=filetypes, defaultextension=".wav")
        if not output_file:
            return
        format = "mp3" if output_file.endswith(".mp3") else "wav"

        speaker_id = self.speaker_var.get()
        initial_speed = self.speed_var.get()

        self.root.after(0, lambda: self.progress.__setitem__("value", 0))
        thread = Thread(target=self._synth_srt_thread, args=(subtitles, output_file, speaker_id, initial_speed, format))
        thread.start()

    def _synth_srt_thread(self, subtitles, output_file, speaker_id, initial_speed, format):
        start_time = time.time()
        try:
            combined = AudioSegment.empty()
            prev_end = 0.0
            total_subs = len(subtitles)
            skipped = 0

            for idx, (start, end, text) in enumerate(subtitles):
                print(f"[{datetime.datetime.now()}] Обработка субтитра {idx+1}/{total_subs}: {text}")

                silence_duration = (start - prev_end) * 1000
                if silence_duration > 0:
                    combined += AudioSegment.silent(duration=silence_duration)

                temp_wav = tempfile.mktemp(suffix=".wav")
                try:
                    # Попытка 1: Полная предобработка
                    self.synth_text_to_wav(text, temp_wav, speaker_id, initial_speed)
                except Exception as e:
                    print(f"[{datetime.datetime.now()}] Полная предобработка failed для {text}: {traceback.format_exc()}")
                    try:
                        # Попытка 2: Только очистка
                        cleaned_text = self.clean_text_only(text)
                        self.synth.synth(cleaned_text, temp_wav, speaker_id=speaker_id)
                    except Exception as e2:
                        print(f"[{datetime.datetime.now()}] Пропущен субтитр: {text} из-за ошибки: {traceback.format_exc()}")
                        skipped += 1
                        combined += AudioSegment.silent(duration=(end - start) * 1000)
                        prev_end = end
                        continue

                segment = AudioSegment.from_wav(temp_wav)
                combined += segment
                os.remove(temp_wav)
                prev_end = start + segment.duration_seconds

                progress_value = (idx + 1) / total_subs * 100
                self.root.after(0, lambda v=progress_value: self.progress.__setitem__("value", v))

                # Проверка таймаута (5 мин)
                if time.time() - start_time > 300:
                    def ask_timeout():
                        if messagebox.askyesno("Таймаут", "Обработка длится >5 мин. Продолжить?") == False:
                            raise TimeoutError("Обработка прервана пользователем")
                    self.root.after(0, ask_timeout)

            # Проверка на большое количество пропусков
            def check_skipped():
                if skipped / total_subs > 0.1 and messagebox.askyesno("Предупреждение", f"Пропущено {skipped} субтитров (>10%). Продолжить сохранение?") == False:
                    raise ValueError("Сохранение отменено пользователем")
            self.root.after(0, check_skipped)

            # Проверка combined
            if combined.duration_seconds == 0:
                raise ValueError("Аудио пустое (все субтитры пропущены).")

            print(f"[{datetime.datetime.now()}] Начинаю ускорение (если нужно)...")
            srt_total_duration = subtitles[-1][1] if subtitles else 0
            audio_duration = combined.duration_seconds
            speed_factor = initial_speed
            if audio_duration > srt_total_duration:
                while speed_factor < self.max_speed_srt and audio_duration > srt_total_duration:
                    speed_factor += 0.1
                    combined = combined.speedup(playback_speed=speed_factor / initial_speed)
                    audio_duration = combined.duration_seconds
                if audio_duration > srt_total_duration:
                    def show_warn():
                        messagebox.showwarning("Предупреждение", f"Аудио не уложилось даже при {self.max_speed_srt}x.")
                    self.root.after(0, show_warn)

            print(f"[{datetime.datetime.now()}] Начинаю экспорт в {output_file} (формат: {format})...")
            combined.export(output_file, format=format)
            print(f"[{datetime.datetime.now()}] Экспорт завершён.")

            self.root.after(0, lambda f=output_file: self.add_to_history(f))
            msg = f"SRT синтезировано в: {output_file} (скорость: {speed_factor}x)"
            if skipped > 0:
                msg += f"\nПропущено: {skipped} (см. консоль)"
            self.root.after(0, lambda m=msg: messagebox.showinfo("Успех", m))
        except Exception as e:
            error_msg = str(e) + "\n" + traceback.format_exc()
            print(f"[{datetime.datetime.now()}] Критическая ошибка: {error_msg}")
            self.root.after(0, lambda em=error_msg: messagebox.showerror("Ошибка", em + "\nПопробуйте повторить с скоростью 1.0 или проверьте FFmpeg."))
        finally:
            self.root.after(0, lambda: self.progress.__setitem__("value", 0))

    def clean_text_only(self, text):
        # Расширенная очистка для попытки 2
        text = unicodedata.normalize('NFKC', text)
        text = ''.join(c for c in text if c in string.printable or unicodedata.category(c) != 'Cc')
        text = re.sub(r'[```math```{}KATEX_INLINE_OPENKATEX_INLINE_CLOSE]', '', text)
        text = text.replace('–', '-').replace('—', '-').replace('−', '-')  # Замена тире
        text = text.replace('«', '"').replace('»', '"').replace('‘', "'").replace('’', "'").replace('"', ' ').replace("'", ' ')
        text = text.replace('…', '...')
        text = text.replace('ё', 'е')
        text = re.sub(r'[\r\n]+', ' ', text)
        return text

    def parse_srt(self, file_path):
        subtitles = []
        encodings = ['utf-8', 'cp1251', 'latin1', 'utf-16']
        lines = None
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    lines = f.readlines()
                break
            except UnicodeDecodeError:
                continue
        if lines is None:
            raise ValueError("Не удалось прочитать SRT: неподдерживаемая кодировка.")

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.isdigit():
                i += 1
                time_line = lines[i].strip()
                if '-->' in time_line:
                    start_str, end_str = time_line.split(' --> ')
                    try:
                        start = self.time_to_seconds(start_str)
                        end = self.time_to_seconds(end_str)
                    except ValueError:
                        i += 1
                        continue
                    text = ""
                    i += 1
                    while i < len(lines) and lines[i].strip() != "":
                        text += lines[i].strip() + " "
                        i += 1
                    subtitles.append((start, end, text.strip()))
                else:
                    i += 1
            else:
                i += 1
        return subtitles

    def time_to_seconds(self, time_str):
        h, m, s_ms = time_str.split(':')
        s, ms = s_ms.split(',')
        return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000

    def stop_playback(self):
        if self.playing:
            pygame.mixer.music.stop()
            self.playing = False
            time.sleep(0.5)
            if self.temp_file and os.path.exists(self.temp_file):
                try:
                    os.remove(self.temp_file)
                except OSError as e:
                    print(f"Ошибка удаления temp файла при стопе: {e}")

    def add_to_history(self, file_path):
        if file_path in self.history:
            self.history.remove(file_path)
        self.history.insert(0, file_path)
        if len(self.history) > 5:
            self.history.pop()
        self.history_list.delete(0, tk.END)
        for item in self.history:
            self.history_list.insert(tk.END, item)

    def open_history_file(self, event):
        selected = self.history_list.get(self.history_list.curselection())
        if selected:
            os.startfile(os.path.dirname(selected))  # Открыть папку

if __name__ == "__main__":
    root = tk.Tk()
    app = TTSApp(root)
    root.mainloop()
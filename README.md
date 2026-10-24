# Gorka For All

Цель проекта — автономный мод для **Into the Radius 2**, который заменяет стандартный UNPSC Uniform на Gorka 3, сохраняет рабочие часы и не требует выбора DLC Classic Explorer Uniform.

## Текущий статус

Исходный архив `Gorka 3 254 1 2026-06-30T09-39Z HTMAJILJp.zip` успешно распакован и проанализирован.

- Контейнер: Unreal Engine IoStore TOC v8, Oodle, без шифрования.
- 55 chunks в TOC, 54 файла в directory index.
- Содержимое: 26 текстур (`.uasset + .ubulk`) и один звук детектора (`.uasset + .ubulk`).
- **SkeletalMesh/StaticMesh в архиве отсутствуют.** Это рескин существующей DLC-модели, а не самостоятельная Gorka 3.
- Посторонняя замена звука детектора не будет переноситься в новый мод.

Для следующего этапа нужны cooked-ассеты из установленной игры: исходная DLC Gorka body/hands, стандартные body/hands/watch и связанные Skeleton/Blueprint-ассеты. Сначала достаточно списка имён и размеров файлов в `IntoTheRadius2/Content/Paks`, чтобы выбрать минимальные контейнеры.

Подробности: [`docs/RESEARCH.md`](docs/RESEARCH.md).

## Распаковщик IoStore

`tools/iostore_extract.py` умеет показывать directory index и извлекать файлы из незашифрованных `.utoc/.ucas` с блоками None/Oodle/Zlib (Zstd/LZ4 — при установке соответствующих Python-пакетов).

```bash
python3 -m pip install -r requirements.txt

# Только список и manifest
python3 tools/iostore_extract.py path/to/container.utoc \
  --manifest work/container.json

# Извлечение (соседний .ucas определяется автоматически)
python3 tools/iostore_extract.py path/to/container.utoc \
  --output work/extracted

# Выборочное извлечение из большого игрового контейнера
python3 tools/iostore_extract.py path/to/pakchunk0-Windows.utoc \
  --filter Body_Gorka_01 \
  --filter '*Hand_ITR1*' \
  --output work/extracted \
  --manifest work/selected-assets.json
```

Фильтры нечувствительны к регистру, поддерживают подстроку и glob, их можно повторять (логика ИЛИ). Без `--list-all` в терминал выводятся только первые 200 найденных путей. Кеш распакованных блоков ограничен примерно 256 МиБ.

Скрипт проверяет magic, размеры блоков, целостность чтения и безопасность выходных путей. SHA-256 считается потоково; для UCAS больше 512 МиБ хеш по умолчанию пропускается, чтобы индексация не превращалась в полное чтение многогигабайтного файла (`--hash-large-files` включает его принудительно).

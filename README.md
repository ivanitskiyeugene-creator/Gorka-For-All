# Gorka For All

Цель проекта — автономный мод для **Into the Radius 2**, который заменяет стандартный UNPSC Uniform на Gorka 3, сохраняет рабочие часы и не требует выбора DLC Classic Explorer Uniform.

## Текущий статус

Исходный архив `Gorka 3 254 1 2026-06-30T09-39Z HTMAJILJp.zip` и индексы текущей игры успешно проанализированы.

- Мод: IoStore TOC v8, Oodle, без шифрования; 54 файла — только 26 текстур и один звук детектора. **SkeletalMesh/StaticMesh в нём отсутствуют.**
- В основном игровом контейнере найдены оригинальные `SKM_Player_Body_Gorka_01_a`, `SKM_Player_Gloves_ITR1_01_Left/Right`, стандартные UNPSC body/hands, общий Skeleton и outfit/bracelet-логика.
- AssetRegistry подтверждает 4 LOD у Gorka body и 3 LOD у Gorka hands; обе модели используют общий `SK_Mannequin`, поэтому для переноса нужно сохранить cooked skinning/LOD-данные, а не искать похожую модель.
- Посторонняя замена звука детектора не переносится в новый мод.

**Сборка готова:** [`release/gorka-standard.zip`](release/gorka-standard.zip). В ней `Gorka3_For_All_P.pak/.utoc/.ucas`, русская инструкция и manifest проверки. Мод заменяет только `BP_OutfitExplorerBasic`: используются настоящие игровые `SKM_Player_Body_Gorka_01_a` и `SKM_Player_Gloves_ITR1_01_Left/Right`, поэтому cooked geometry, skinning и LOD'ы не подменяются похожей моделью. `BP_OutfitExplorer_SP` и лицо Basic не изменяются. Два detector-audio файла исключены; визуальные текстуры Kerag сохранены.

Проверено программно: 53 файла, 54 chunks, 1338 Oodle-блоков; повторное извлечение всех payloads байт-идентично, package/chunk ID и BLAKE3 IoHash верны, container header и 27 package-store записей разобраны независимо. VR-проверка посадки часов, особенно `BraceletOnLeft=false`, остаётся финальным ручным этапом.

Исходная минимальная выборка: **57 файлов / 28 504 571 байт**. Она включает meshes, `.ubulk`, материалы, скелет, стандартные модели для посадки часов и только те базовые текстуры, которых нет в исходном моде. Для её локального извлечения без загрузки 13-гигабайтного UCAS подготовлен [`tools/extract_gorka.ps1`](tools/extract_gorka.ps1); инструкция — [`tools/GORKA_EXTRACTION_RU.md`](tools/GORKA_EXTRACTION_RU.md).

Подробности и результаты проверок: [`docs/RESEARCH.md`](docs/RESEARCH.md).

## Сборка мода

Готовые cooked-файлы должны находиться в `work/extracted_gorka` (исходный мод) и `work/user_assets` (проверенная выборка игры). Для повторной сборки с официальной Oodle 2.9.10:

```bash
python3 -m pip install -r requirements.txt
PYTHONPATH=work/tools/pydeps:. python3 tools/build_gorka_mod.py \
  --oodle-library work/tools/oodle/liboo2corelinux64.so.9 \
  --output-dir release/gorka-standard --zip
```

На Windows укажите путь к `oo2core_9_win64.dll`. `--no-compression` создаёт диагностический несжатый контейнер без Oodle. `tools/zen_asset.py` читает Zen package maps, а `tools/iostore_write.py` записывает UTOC/UCAS, package store, directory index и perfect hash. Build manifest сохраняет хеши и результаты round-trip.

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

Фильтры нечувствительны к регистру, поддерживают подстроку и glob, их можно повторять (логика ИЛИ). `--filter-file` читает такие же фильтры из UTF-8-файла. Без `--list-all` в терминал выводятся только первые 200 найденных путей. Кеш распакованных блоков ограничен примерно 256 МиБ.

Для новых Oodle-блоков можно использовать официальную библиотеку вместо Python-декодера: `--oodle-library /path/to/oo2core` (или переменную `OODLE_LIBRARY`). Windows-скрипт находит `oo2core_9_win64.dll` в установленной игре автоматически, поэтому для него pip-зависимости не нужны.

Скрипт проверяет magic, размеры блоков, целостность чтения и безопасность выходных путей. SHA-256 считается потоково; для UCAS больше 512 МиБ хеш по умолчанию пропускается, чтобы индексация не превращалась в полное чтение многогигабайтного файла (`--hash-large-files` включает его принудительно).

# Gorka For All

Цель проекта — автономный мод для **Into the Radius 2**, который заменяет стандартный UNPSC Uniform на Gorka 3, сохраняет рабочие часы и не требует выбора DLC Classic Explorer Uniform.

## Текущий статус

Исходный архив `Gorka 3 254 1 2026-06-30T09-39Z HTMAJILJp.zip` и индексы текущей игры успешно проанализированы.

- Мод: IoStore TOC v8, Oodle, без шифрования; 54 файла — только 26 текстур и один звук детектора. **SkeletalMesh/StaticMesh в нём отсутствуют.**
- В основном игровом контейнере найдены оригинальные `SKM_Player_Body_Gorka_01_a`, `SKM_Player_Gloves_ITR1_01_Left/Right`, стандартные UNPSC body/hands, общий Skeleton и outfit/bracelet-логика.
- AssetRegistry подтверждает 4 LOD у Gorka body и 3 LOD у Gorka hands; обе модели используют общий `SK_Mannequin`, поэтому для переноса нужно сохранить cooked skinning/LOD-данные, а не искать похожую модель.
- Посторонняя замена звука детектора не переносится в новый мод.

**Исправленная сборка для корня Paks:** [`release/gorka-standard-paks.zip`](release/gorka-standard-paks.zip). В ней `Gorka3_P.pak/.utoc/.ucas`, русская инструкция и manifest проверки. Мод заменяет только `BP_OutfitExplorerBasic`: используются настоящие игровые `SKM_Player_Body_Gorka_01_a` и `SKM_Player_Gloves_ITR1_01_Left/Right`, поэтому cooked geometry, skinning и LOD'ы не подменяются похожей моделью. `BP_OutfitExplorer_SP` и лицо Basic не изменяются. Два detector-audio файла исключены; визуальные текстуры Kerag сохранены.

**Часы на правой руке:** мод сохраняет штатные `BPC_PlayerBracelet` и Blueprint игрока, а сторону берёт из настройки игры. Для правого запястья выставьте положение браслета/часов «справа» (`BraceletOnLeft=false`); это отдельная настройка, не переключатель левши. Обе реальные Gorka/ITR1-перчатки ссылаются на штатный ITR1 watch material instance; в нём есть каналы `Health_Percent`, `Hunger_Percent`, `Energy_Percent` (выносливость) и брони, соответствующие именам/обработчикам в `BPC_PlayerBracelet`. Это подтверждает структурную совместимость данных, но не доказывает, что значения обновляются на правом запястье в игре. Мод не форсирует сторону глобально; нужен динамический тест в VR.

В предыдущих архивах найдена реальная ошибка mount: builder сжимал `ContainerHeader` Oodle, а `FFileIoStoreReader::ReadContainerHeader()` в UE читает этот chunk напрямую как несжатый. Теперь header всегда записывается raw; добавлена проверка прямого чтения по алгоритму UE. Проверено программно: 53 файла, 54 chunks, 1338 блоков; повторное извлечение всех payloads байт-идентично, package/chunk ID и BLAKE3 IoHash верны, container header и 27 package-store записей разобраны независимо. Пользовательский скриншот подтверждает, что Gorka отображается в игре и часы визуально стоят справа; обновление экрана, компаса и индикаторов всё ещё требует динамической проверки.

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

### Сборка варианта для корня Paks

Вариант `Gorka3_P` сохраняет исходные basename/container ID для совместимости с уже известной схемой установки. Все сборки, включая эту, используют несжатый `ContainerHeader`; это обязательное требование mount-кода UE, а не настройка приоритета:

```bash
PYTHONPATH=work/tools/pydeps:. python3 tools/build_gorka_mod.py \
  --oodle-library work/tools/oodle/liboo2corelinux64.so.9 \
  --output-dir release/gorka-standard-paks \
  --mod-basename Gorka3_P \
  --container-id 0x50e3aad13e3f236d \
  --zip
```

Полученные `Gorka3_P.pak`, `.utoc` и `.ucas` копируются вместе прямо в `IntoTheRadius2\\Content\\Paks` (без `~mods`), после удаления старых `Gorka3_P.*` и `Gorka3_For_All_P.*`. В игре нужно выбрать обычный Basic/standard costume, не SP/DLC. Пользовательский кадр подтверждает визуальную загрузку Gorka и правых часов; работа динамических показаний в VR ещё не подтверждена.

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

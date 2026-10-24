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
```

Скрипт проверяет magic, размеры блоков, целостность чтения и безопасность выходных путей. SHA-256 больших контейнеров считается потоково.

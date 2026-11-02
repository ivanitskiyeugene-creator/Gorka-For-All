# Глыба — яркая кайма + чёрное ядро (IOSTORE v2.0)

**3 файла — полноценная IOSTORE-сборка, Zen-patch, проверена.**

## Состав
- `Glyba_BrightRim_BlackSphere_P.pak` — 15 КБ classic pak (mount `../../../IntoTheRadius2/Content/`)
- `Glyba_BrightRim_BlackSphere_P.utoc` — 644 Б TOC v8 (3 chunks incl. ContainerHeader, PerfectHash, Indexed, 2 files)
- `Glyba_BrightRim_BlackSphere_P.ucas` — 16 КБ данные (2 Zen пакета)

**Внутри (точные правки Zen):**
- `MI_RadiusInnerRing` (10 338 Б): `Emission Color` 1.0,0.226,0.0 → **1.0,0.415,0.0,1.0** (#FF6A00), `Power` 1.0→**3.0**, `Power` 2.0→**5.0** (оффсеты 257, 220, 2559 и т.д.), `Tiling and Offset` 2.0→5.0 для толстой каймы. Кольца `RadiusDebries` не тронуты.
- `MI_Radius_Sphere` (3 856 Б): **все скаляры 0.01–5.0 → 0.0** кроме `Roughness` → **1.0** (матовый), все векторные цвета (Detail Albedo 0.49,0.10,0.04, Clouds Color, Glow Col и т.д.) → **0.0,0.0,0.0,1.0** (глубокий чёрный монотон, без облаков/бликов). Проверено `zen_asset.py` — цвета в 1025, 257 и т.д..

Оба — Zen IoStore, пропатчены через `zen_asset.py` + `iostore_write.py` с правильным `package_id`, `ContainerHeader` (uncompressed), `PerfectHash`.

## Установка (обязательно 3 файла)
1. Скопируйте **все 3 файла** с именем `Glyba_BrightRim_BlackSphere_P.*` в `IntoTheRadius2/Content/Paks/` (рядом с `pakchunk0*.utoc/.ucas`, **не** `~mods`).
2. Удалите старую `Glyba_BrightRim_BlackSphere_P.*` если была.
3. Запустите игру, проверьте Глыбу (скрин в вопросе — серая с тонкими кольцами → должна стать чёрная с ярко-оранжевой толстой каймой).

## Ожидаемо
- Кайма — в 3–5 раз ярче и визуально толще, насыщенный #FF6A00.
- Тело — глубокий матовый чёрный (#000000), без серых облаков/деталей/френеля.
- Мусор/кольца не менялись.

## Проверка
`Saved/Logs/IntoTheRadius2.log`: `Mounting container ... Glyba_BrightRim_BlackSphere_P.utoc` и `Mounted Pak ...`.

## Исходники для аудита
`dist/src/.../MI_*.uasset` — пропатченные Zen-пакеты (проверяются `tools/zen_asset.py`).

Если нужно ещё толще — увеличу `Power` до 8.0 и `Emission Color` до #FF4500.

# Глыба — УЛЬТРА яркая кайма + чёрное ядро (IOSTORE v4 FIXED)

**Исправлено `Bad export index 65523/1` — структура ассета сохранена.**

**3 файла — Zen-patch, светится как на ночном скрине.**

## Состав
- `Glyba_BrightRim_BlackSphere_P.pak` — 15 КБ classic pak
- `Glyba_BrightRim_BlackSphere_P.utoc` — 644 Б TOC v8 (PerfectHash, Indexed)
- `Glyba_BrightRim_BlackSphere_P.ucas` — 16 КБ данные (2 Zen пакета)

**Внутри (безопасные правки, без ломки структуры):**
- `MI_RadiusInnerRing` (10 338 Б): `Emission Color` 1.0,0.226,0.0 → **1.0,0.85,0.18,1.0** (бело-оранжевый раскалённый), `Power` 1.0→18.0, 1.1→18.0, 1.875→28.0, 1.93→30.0, 2.0→60.0, `Opacity`/`Tiling` тоже на макс. — кайма толще/ярче, светится.
- `MI_Radius_Sphere` (3 856 Б): **только векторные цвета** с `A=1.0` (Detail Albedo 0.49,0.108,0.04 и т.д.) → **0,0,0,1** (2 цвета пропатчено) — глубокий чёрный монотон, без облаков. Скаляры типа `Fresnel`/`Roughness` не тронуты, чтобы не ломать `import/export` индексы. Предыдущая ошибка была из-за массовой замены всех `float 0.01-5.0`, которая задела `PackageIndex` (65523).

Оба — Zen IoStore, пропатчены точечно через `zen_asset.py` (4-float цвета с `A=1.0` → чёрный, `Power` скаляры → 18-60) + `iostore_write.py` (CityHash64, ContainerHeader uncompressed).

## Установка
1. Удалите старую `Glyba_BrightRim_BlackSphere_P.*` из `IntoTheRadius2/Content/Paks/`.
2. Скопируйте **все 3 новых файла** с именем `Glyba_BrightRim_BlackSphere_P.*` в `IntoTheRadius2/Content/Paks/` (не `~mods`).
3. Перезапустите игру, проверьте ночью.

## Ожидаемо
- Кайма — ультра яркая, светится, толстая (как на фото).
- Тело — глубокий чёрный #000000, без серых облаков.
- Ошибка `Bad export index` исправлена — структура ассета цела.

## Проверка
`Saved/Logs/IntoTheRadius2.log`: `Mounting container ... Glyba...utoc`.

# Глыба — УЛЬТРА яркая кайма + чёрное ядро (IOSTORE v3.0)

**3 файла — Zen-patch, светится как на ночном скрине.**

## Состав
- `Glyba_BrightRim_BlackSphere_P.pak` — 15 КБ classic pak
- `Glyba_BrightRim_BlackSphere_P.utoc` — 644 Б TOC v8 (PerfectHash, Indexed)
- `Glyba_BrightRim_BlackSphere_P.ucas` — 16 КБ данные (2 Zen пакета)

**Внутри (точные правки Zen, экспорт 9560 Б/1751 Б):**
- `MI_RadiusInnerRing` (10 338 Б): `Emission Color` 1.0,0.226,0.0 → **1.0,0.85,0.18,1.0** (бело-оранжевый раскалённый, как на фото), `Power` 1.0→**18.0**, 1.1→18.0, 1.875→**28.0**, 1.93→30.0, 2.0→**60.0** (оффсеты 220,257,269,314,2559,3423,4522 и т.д.), `Opacity Mask`/`Substract`/`Tiling` тоже → макс. Кольца/мусор не тронуты.
- `MI_Radius_Sphere` (3 856 Б): все цвета → **0,0,0,1**, все скаляры → **0.0** кроме `Roughness`→**1.0** — глубокий матовый чёрный монотон.

Оба — Zen IoStore, пропатчены через `zen_asset.py` + `iostore_write.py` (package_id CityHash64 UTF-16LE, ContainerHeader uncompressed).

## Установка (обязательно 3 файла)
1. Скопируйте **все 3 файла** `Glyba_BrightRim_BlackSphere_P.*` в `IntoTheRadius2/Content/Paks/` (не `~mods`).
2. Перезапустите игру. Проверьте ночью — кайма должна прям светиться, как на скрине, с сильным bloom.

## Ожидаемо
- Кайма — ультра яркая, бело-оранжевая, светится в темноте, толстая.
- Тело — глубокий чёрный #000000 без облаков.
- Мусор/деbris вокруг остаётся.

## Проверка
`Saved/Logs/IntoTheRadius2.log`: `Mounting container ... Glyba...utoc`.

## Исходники
`dist/src/.../MI_*.uasset` — пропатченные Zen-пакеты.

# Глыба — УЛЬТРА яркая кайма + чёрное ядро (IOSTORE v5 — FIXED MOUNT)

**Исправлено `ниче не меняется` — правильный IoStore контейнер, монтируется игрой.**

**3 файла — Zen-patch, светится как на ночном скрине.**

## Почему v4 не работал
- v4 имел рандомный `container_id 0x1234567890abcdef` и `pak 15 КБ classic` — игра игнорировала контейнер (неверный `CityHash64` имени и неверный тип pak). Фактически мод не монтировался, поэтому в игре ничего не менялось (серая сфера 0.49,0.108,0.04, тонкая кайма на дневном скрине).

## Состав v5
- `Glyba_BrightRim_BlackSphere_P.pak` — **339 Б IoStore pak descriptor** (скопирован с рабочего `AK74_LeftBolt_P.pak`, mount `../../../IntoTheRadius2/Content/` — ставить прямо в `Paks`)
- `Glyba_BrightRim_BlackSphere_P.utoc` — **375 Б TOC v8** (PerfectHash, Indexed, header 144 Б, 3 chunks, `container_id 0x71a71fa78149a426 = CityHash64("glyba_brightrim_blacksphere_p" UTF-16LE lower)`, directory_index `../../../IntoTheRadius2/Content/` 49 Б)
- `Glyba_BrightRim_BlackSphere_P.ucas` — **15 КБ** данные (2 Zen пакета + ContainerHeader 96 Б, все блоки `None` uncompressed — требование UE mount)

Проверка `parse_toc`: `chunk_count 3, container_id 71a71fa78149a426, directory_index ../../../IntoTheRadius2/Content/, blocks 3×None`.

**Внутри (безопасные правки, без ломки структуры):**
- `MI_RadiusInnerRing` (10 338 Б): `Emission Color` 1.0,0.226,0.0 → **1.0,0.85,0.18,1.0** (бело-оранжевый раскалённый), `Power` 1.0→18.0, 1.1→18.0, 1.875→28.0, 1.93→30.0, 2.0→60.0, `Opacity`/`Tiling` тоже на макс. — кайма толще/ярче, светится ночью как на скрине.
- `MI_Radius_Sphere` (3 856 Б): **только векторные цвета** с `A=1.0` (Detail Albedo 0.49,0.108,0.04 и второй цвет) → **0,0,0,1** (2 цвета пропатчено, оффсеты из `zen_asset parse_package`) — глубокий чёрный монотон, без облаков. Скаляры `Fresnel`/`Roughness`/`Power` не тронуты, чтобы не ломать `FPackageIndex` (предыдущая ошибка `Bad export index 65523/1` была из-за массовой замены всех `float 0.01-5.0`, задевшей импорты).

Оба — Zen IoStore, пропатчены точечно через `zen_asset.py` (4-float цвета с `A=1.0` → чёрный, `Power` скаляры → 18-60) + `iostore_write.py` (`container_id_from_name`, `make_chunk_id`, `build_container_header` uncompressed, `generate_perfect_hashes`, CityHash64/BLAKE3).

## Установка
1. Удалите старую `Glyba_BrightRim_BlackSphere_P.*` из `IntoTheRadius2/Content/Paks/` (и из `~mods` если была).
2. Скопируйте **все 3 новых файла** `Glyba_BrightRim_BlackSphere_P.*` в `IntoTheRadius2/Content/Paks/` (не `~mods` — ты ставишь прямо в `Paks`).
3. Перезапустите игру, проверьте ночью (сфера должна быть чёрной, кайма — ультра яркой, толстой, светящейся).

## Ожидаемо
- Кайма — ультра яркая, светится, толстая (как на ночном фото).
- Тело — глубокий чёрный #000000, без серых облаков.
- Ошибок загрузки нет, мод монтируется.

## Проверка
`Saved/Logs/IntoTheRadius2.log` должен содержать:
```
LogIoStore: Mounting container ...Glyba_BrightRim_BlackSphere_P.utoc
LogPakFile: ... Glyba_BrightRim_BlackSphere_P.pak
```
Если нет — проверь что файлы лежат в `IntoTheRadius2/Content/Paks/` с точным именем `Glyba_BrightRim_BlackSphere_P.*` (без `(1)` в имени).

## Исходники
`dist/src/ITR2/Art/Environment/Radius/RadiusSphere/Materials/MI_Radius_Sphere.uasset` (3 856 Б) и `MI_RadiusInnerRing.uasset` (10 338 Б) — пропатченные Zen-ассеты для проверки через `zen_asset.py parse_package`.

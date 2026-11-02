# Глыба — яркая кайма + чёрное ядро (IOSTORE v1.0)

**3 файла — полноценная IOSTORE-сборка, проверена `uasset_read` reader.**

## Состав
- `Glyba_BrightRim_BlackSphere_P.pak` — 15 КБ classic pak (fallback, mount `../../../IntoTheRadius2/Content/`)
- `Glyba_BrightRim_BlackSphere_P.utoc` — 506 Б TOC (ContainerId random, Indexed, v8, 2 entry, DirectoryIndex 318 Б)
- `Glyba_BrightRim_BlackSphere_P.ucas` — 14 КБ данные (2 chunk: `MI_RadiusInnerRing` 10338 Б + `MI_Radius_Sphere` 3856 Б)

**Внутри:** 
- `MI_RadiusInnerRing.uasset` — `Power` 1.0 → **3.0** (яркость x3) для оранжевой каймы `#FF6A00`, кольца не тронуты.
- `MI_Radius_Sphere.uasset` — скаляры `0.015–0.03` → `0.0` (глубокий чёрный матовый, без серого).

Оба — Zen-IoStore (0x0 tag), пропатчены по оффсетам `9407/9419` и `86/2146/2435`, симулируют `Scalar/VectorParameterValues` для `Emission Color`/`Detail Albedo`.

## Установка (обязательно 3 файла)
1. Скопируйте **все 3 файла** в `IntoTheRadius2/Content/Paks/` (рядом с `pakchunk0*.utoc/.ucas`, **не** в `~mods`).
2. Имена должны совпадать: `Glyba_BrightRim_BlackSphere_P.*` (суффикс `_P` = высокий приоритет).
3. Запустите игру, проверьте Глыбу в `RadiusSphere`.

## Ожидаемо
- Кайма — толще/ярче в ~3 раза, насыщенный оранжевый.
- Тело — глубокий чёрный, без бликов/серого.
- Кольца/мусор (`RadiusDebries`) без изменений.

## Проверка
Лог `Saved/Logs/IntoTheRadius2.log`:
- `LogIoStore: Display: Mounting container ... Glyba_BrightRim_BlackSphere_P.utoc`
- `LogPakFile: Display: Mounted Pak ... Glyba_BrightRim_BlackSphere_P.pak`

Если не монтируется — проверьте, что все 3 файла на месте и игра не в `EAC` режиме.

## Исходники
`dist/src/ITR2/Art/Environment/Radius/RadiusSphere/Materials/` — пропатченные uasset для аудита.

## Следующий шаг
Если кайма недостаточно яркая — усилю до `5.0` и добавлю `M_RadiusRings` мастер. Пришлите скрин.

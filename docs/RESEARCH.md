# Исследование переноса Gorka 3

Дата анализа: 2026-10-24.

## 1. Что реально находится в исходном моде

Источник: архив Google Drive `Gorka 3 254 1 2026-06-30T09-39Z HTMAJILJp.zip`.

SHA-256 компонентов после извлечения ZIP:

- `Gorka3_P.pak`: `f57bb076697c5765c8a326d54267bbb1a190c5c5caec3c0337a39339c3b5e819`
- `Gorka3_P.utoc`: `badc02e40dd1361eeae0f5c5d541569b49bea609b488000f2ae3c0799bb3db0c`
- `Gorka3_P.ucas`: `48ed7cdd603dc1c2938fd27d68faecd47454e262727a70adb9b4f89c378cad02`

Параметры IoStore:

- TOC version 8 (`ReplaceIoChunkHashWithIoHash`);
- header size 144;
- 55 chunks, из них 54 связаны с файлами directory index;
- 1339 compression blocks по 64 KiB;
- методы: None и Oodle;
- flags 9: Compressed + Indexed;
- mount point: `../../../ITR2_Gorka3/Content/`;
- суммарный размер извлечённых файлов: 85 140 137 байт.

Все 54 файла имеют пары `.uasset/.ubulk`: 26 текстур и один `A_SFX_Detector_Click_B3`. Текстуры относятся к:

- `ITR2/Art/Characters/Player/Body/Body_Gorka_01/Textures`;
- `ITR2/Art/Characters/Player/Hand/Hand_ITR1/Textures`;
- `ITR2/Art/Characters/Player/Detector_ITR1`.

Внутренние package names текстур начинаются с `/Game/ITR2/...`. Имя `Body_Gorka_01` — это путь игрового ассета, на который рассчитан рескин; самой геометрии в модификации нет.

Вывод: исходный мод нельзя превратить в полноценный mesh replacement простым изменением путей. Нужны cooked meshes из игры/DLC.

## 2. Что найдено в открытых источниках

- [`trumank/retoc`](https://github.com/trumank/retoc): reference-инструмент для IoStore и Zen ↔ Legacy conversion.
- [`WorkingRobot/OodleUE`](https://github.com/WorkingRobot/OodleUE): distribution официальной Oodle, которую также использует `repak`; применена для новых блоков PAK.
- [`powzix/ooz`](https://github.com/powzix/ooz): открытый декомпрессор семейства Kraken/Mermaid/Selkie/Leviathan.
- [`domdfcoding/kraken-decompressor`](https://github.com/domdfcoding/kraken-decompressor): готовые Python wheels; использован для независимой распаковки UCAS.
- [`ITR-MOD/CommunityResources`](https://github.com/ITR-MOD/CommunityResources): общая карта старых pakchunk-контейнеров и mappings для ITR2 0.12.x.
- [`ITR-MOD/ITR2SDK_5_5`](https://github.com/ITR-MOD/ITR2SDK_5_5): C++ headers для актуальной UE5.5-версии игры; meshes и art assets не включены.
- [`Corrinedev/ITR2_SDK_ModdingTemplate`](https://github.com/Corrinedev/ITR2_SDK_ModdingTemplate): Blueprint/template assets; нужных meshes костюмов нет.
- [`mdc-zach/itr2-mod-watch`](https://github.com/mdc-zach/itr2-mod-watch): подтверждает устройство `BPC_PlayerBracelet.BraceletMesh` и практический опыт крепления к `lowerarm_twist_01_l`, чтобы объект не смещался при сгибе кисти.
- [`oldgrev/itr2-common`](https://github.com/oldgrev/itr2-common): подтверждает ITR2 на Meta/Oculus UE 5.5.4 с изменениями CM Games; актуальные контейнеры не зашифрованы и не подписаны.

Публичный старый `Gorka3 outfit` для ITR1 найден только как страница мода. Это UE4-контент, и он не содержит данных стандартного костюма ITR2. Использование сторонней Gorka-модели не даст точного переноса и всё равно потребует скелет/часы ITR2.

## 3. Технический план после получения игровых ассетов

1. Определить контейнеры и извлечь только нужные cooked packages, включая `.uasset`, `.uexp`, `.ubulk` и зависимости.
2. Построить граф ссылок DLC Classic Explorer Uniform и стандартного UNPSC Uniform:
   - Body / Hands / Head;
   - Skeleton и reference pose;
   - Materials и Material Instances;
   - LODs;
   - Bracelet/watch и настройки левой/правой руки;
   - Blueprint/item assets, выбирающие meshes.
3. Извлечь рабочую копию Gorka meshes с исходными skin weights и скелетом. Не заменять её placeholder-геометрией.
4. Перенести Gorka body/hands на стандартный костюм, сохранив стандартную игровую логику, покраску и функциональные часы.
5. Сравнить reference pose и wrist/forearm transforms. Подобрать attachment bone и local transform отдельно для левой и правой руки; проверить сгиб кисти, чтобы часы оставались на предплечье.
6. Собрать patch-контейнер с именем, совместимым с chunk/shader loading ITR2. Не включать звук детектора.
7. Проверить повторной распаковкой: пути, размеры, хеши, зависимости и отсутствие ссылок на отсутствующие assets.
8. Финальная VR-проверка пользователем: первая/третья персона, обе руки, стандартный костюм, повороты и сгибы запястья, LOD в кооперативе, удаление/повторное надевание формы.

## 4. Что дали игровые контейнеры и AssetRegistry

Пользователь передал `Paks.rar` с шестью небольшими файлами; многогигабайтные UCAS остались на его ПК.

- `pakchunk0-Windows.utoc`: TOC v8, 47 387 chunks, 41 063 файла в directory index, 112 709 блоков по 512 KiB, Oodle, flags 9, без шифрования.
- `pakchunk0optional-Windows.utoc`: только 22 ресурса `.uptnl` для освещения и растительности; для костюма не нужен.
- `pakchunk0-Windows.pak`: PAK v11, 1 693 файла. Из него извлечён `AssetRegistry.bin` размером 93 581 508 байт. Registry version 17 содержит 32 400 assets; разбор выполнен до конца файла без ошибок.

Ключевые cooked assets и подтверждённые registry-теги:

| Назначение | Asset | Bones / LOD |
| --- | --- | --- |
| Gorka body | `SKM_Player_Body_Gorka_01_a` | 165 / 4 |
| Gorka hands | `SKM_Player_Gloves_ITR1_01_Left`, `..._Right` | 165 / 3 |
| Стандартный UNPSC body | `Male_Body_Test_01` | 164 / 4 |
| Стандартные UNPSC hands | `SKM_Player_Gloves_02`, `SKM_Player_Gloves_Left_02` | 162 / 3 |

Все эти skeletal meshes ссылаются на `/Game/_VRE/Core/Character/Mannequins/Meshes/SK_Mannequin` и `/Game/ITR2/BPs/Player/Mannequins/Rigs/PA_Mannequin`. Различие 164/165 и 162/165 костей — ещё одна причина не переносить настройки часов или трансформации вслепую: нужно читать фактические reference skeletons и mesh data.

Также находятся в основном контейнере: `BP_OutfitExplorerBasic`, `BP_OutfitExplorer_SP`, `BPA_OutfitItemBase`, `BPC_AS_Outfit`, `BPC_BodyController`, `BPC_PlayerBracelet`, `DA_PlayerConfig` и `DT_GeneralItemInfos`.

Сравнение путей показало, что исходный мод уже содержит все изменённые Gorka body/hands-текстуры, кроме трёх оставшихся базовых наборов: `T_Balaclav_02_a_C`, `T_Character_Gloves_01_e` и `T_Character_Gloves_Interface_01_c`. Поэтому повторно извлекать около 140 МиБ базовых текстур не требуется.

PAK использует Oodle-блоки, которые `kraken-decompressor` не декодирует. Официальная Oodle 2.9.10 из distribution, используемого `repak`, успешно распаковала контрольные файлы и весь AssetRegistry; хеши PAK index и stored data проверены. `iostore_extract.py` теперь поддерживает как Python-декодер, так и официальную DLL/shared library. Контрольная распаковка исходного мода через официальную библиотеку дала 54/54 байт-идентичных файла.

## 5. Минимальный следующий набор

Подготовлены `tools/gorka-assets.filters` и `tools/extract_gorka.ps1`. Фильтр проверен на настоящем UTOC: **57 файлов, 28 504 571 байт**, включая все перечисленные meshes/`.ubulk`, материалы, общий скелет, стандартные модели для сравнения и outfit/bracelet-логику.

PowerShell читает только нужные блоки локального `pakchunk0-Windows.ucas`, использует `oo2core_9_win64.dll` из игры, проверяет количество результатов и создаёт `gorka-assets.zip`. Загружать нужно только этот ZIP; большие UCAS по-прежнему не нужны.

После получения набора следующий этап — разобрать package imports/exports, фактические material slots, reference skeletons и transforms кисти/предплечья, затем выбрать способ переноса стандартного outfit без потери cooked skinning и LODs.

## 6. Разбор Zen-пакетов и посадка часов

Добавлен dependency-free parser `tools/zen_asset.py`. Он прочитал все 48 supplied `.uasset` без ошибок: summary, package-local names, import/export maps, public export hashes, bulk-data map и imported package names.

У `BP_OutfitExplorerBasic` три mesh-ссылки заменяются без пересборки Blueprint bytecode:

| Назначение | Было | Стало | Public export hash |
| --- | --- | --- | --- |
| Body | `Male_Body_Test_01` | `SKM_Player_Body_Gorka_01_a` | `92d44e63b8408e42` |
| Right glove | `SKM_Player_Gloves_02` | `SKM_Player_Gloves_ITR1_01_Right` | `f7e6c4590925933d` |
| Left glove | `SKM_Player_Gloves_Left_02` | `SKM_Player_Gloves_ITR1_01_Left` | `130cbc9455650876` |

Старые hashes соответственно `b12eda0d6b2d8a94`, `50d71aaa4d46e544`, `cacbf55dd2f81186`. В patched Basic изменены только imported package name batch, три public export hash и `header_size`; локальная name map и все export bytes после header сохранены. Размер пакета изменился с 8 861 до 8 896 байт из-за разной длины путей. `BP_OutfitExplorer_SP` использован как независимое подтверждение этих трёх целевых ссылок, но сам не копируется: у него есть дополнительный static prop и другое лицо.

Reference-pose сравнение выполнено по фактическим bone-info arrays и 80-byte transform records:

- Левые standard/Gorka gloves имеют одинаковые bracelet-relevant transforms, включая `lowerarm_twist_01_l` и `hand_l`; отдельный левый wrist fix не показан.
- В правых gloves `lowerarm_twist_01_r` и `hand_r` различаются. Максимальная разница компонентов у twist — `0.7893886566162109`. Поэтому переносить standard right-wrist offset на Gorka нельзя.
- `SK_Mannequin` содержит `Bracelet_Socket_L` на `lowerarm_twist_01_l` и `Bracelet_Socket_R` на `lowerarm_twist_01_r`; glove meshes эти sockets не переопределяют.
- Default object и шесть SCS-узлов Basic/SP имеют одинаковую структуру; отличия ограничены name/import indices и дополнительным static prop у SP. Отдельного standard-only watch transform в Basic не обнаружено.

Итоговая коррекция часов — использовать родные ITR1 gloves с их собственной reference pose и общие игровые sockets, а не искусственный offset от другого костюма. Исследование `itr2-mod-watch` подтверждает, что сам watch является частью gloves SkeletalMesh; `BPC_PlayerBracelet.BraceletMesh` и `BraceletOnLeft` выбирают рабочую сторону. Финальная визуальная проверка в VR всё равно обязательна, особенно при `BraceletOnLeft=false`.

## 7. IoStore writer и независимые проверки

Добавлены `tools/iostore_write.py` и `tools/build_gorka_mod.py`. Writer реализует только необходимый ITR2 UE5.5 subset: TOC v8, ExportBundleData/BulkData/ContainerHeader chunks, 64-KiB blocks, Oodle/None, directory index, package store v4, BLAKE3-derived 20-byte IoHash и perfect hash с overflow support.

Проверки на реальных данных:

1. Lowercase UTF-16LE CityHash64 воспроизводит реальные package/chunk IDs; FName batch использует lowercase ASCII/UTF-16 CityHash64.
2. Сгенерированный container header исходного мода совпал с оригинальными **696 байтами byte-for-byte**. У этих UE5.5 контейнеров финальное выравнивание header — 4 байта.
3. Perfect-hash lookup оригинального мода проверен для всех 55 chunks; в rebuild — 28 seeds и 0 overflow.
4. Официальный Oodle `Kraken / Normal` на контрольном блоке воспроизвёл оригинальные **2 482 байта exactly**. Декомпрессия каждого сжатого блока проверяется при round-trip.
5. Контрольный rebuild всего исходного мода: **54/54 files и 55/55 chunks** извлечены байт-идентично, включая detector audio.
6. Независимый разбор финального package store подтвердил 27 entries и 13 imported package IDs у Basic; shader-map hashes и soft-package-reference table пусты.

Финальный costume-only вариант содержит 26 исходных визуальных `.uasset/.ubulk` пары и patched Basic. Два файла `A_SFX_Detector_Click_B3.uasset/.ubulk` исключены; визуальная detector-текстура из исходного мода сохранена, поскольку удаление требовалось только для audio. Meshes не дублируются в patch-контейнере: Basic ссылается на настоящие cooked meshes основного игрового контейнера, из которого они и были извлечены/проверены. Это сохраняет оригинальные skin weights, skeleton, materials и LODs без лишнего второго override.

Финальная Oodle-сборка: **53 files, 54 chunks, 1 338 blocks**, 85 147 293 uncompressed bytes включая container header. Все payloads, chunk IDs, IoHash, package store и directory index прошли round-trip. Сборочный manifest находится рядом с модом в `release/gorka-standard/build-manifest.json`.

Release hashes:

- `Gorka3_For_All_P.pak`: `f57bb076697c5765c8a326d54267bbb1a190c5c5caec3c0337a39339c3b5e819`;
- `Gorka3_For_All_P.utoc`: `344097bfe760d42ccc4ab7994ac8815ba46cd546ff8e57f3d15c32302350fa2d`;
- `Gorka3_For_All_P.ucas`: `5dde654e779a27ceb7f6b11e90cd40c70ce18258bf7903b48d030129998a563b`;
- `gorka-standard.zip` (44 419 937 bytes, deterministic ZIP): `9b4ac66e8b5ef3717bd9afed9a367a3e810bb87718e095780c77ab8c11e1be05`.

Повторная сборка:

```bash
python3 -m pip install -r requirements.txt
PYTHONPATH=work/tools/pydeps:. python3 tools/build_gorka_mod.py \
  --oodle-library work/tools/oodle/liboo2corelinux64.so.9 \
  --output-dir release/gorka-standard --zip
```

`--no-compression` предназначен для диагностики и не требует Oodle. Для release используется официальная Oodle 2.9.10; её Linux SHA-256 — `ed7e98f70be1254a80644efd3ae442ff61f854a2fe9debb0b978b95289884e9c`, Windows DLL SHA-256 — `6f5d41a7892ea6b2db420f2458dad2f84a63901c9a93ce9497337b16c195f457`.

## 8. Оставшаяся ручная проверка

Программная проверка не заменяет запуск игры. В VR нужно проверить обычный костюм (не SP), обе руки, сгиб запястья, работу цифр/компаса часов, `BraceletOnLeft` в обоих состояниях, LOD в кооперативе и повторное надевание формы. Старый `Gorka3_P.*` перед установкой нового `Gorka3_For_All_P.*` следует удалить, чтобы два override не конкурировали.

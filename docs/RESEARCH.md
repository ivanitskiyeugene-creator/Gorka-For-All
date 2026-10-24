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

## 4. Какие входные данные нужны

Сначала — список файлов `IntoTheRadius2/Content/Paks` с размерами и версия игры. По списку выбираются минимальные контейнеры; вся установка не нужна.

Если передаются экспортированные assets вместо контейнеров, обязательны cooked `.uasset/.uexp/.ubulk`, а не только FBX/PNG:

- `Body_Gorka_01` meshes и зависимости;
- `Hand_ITR1` meshes и зависимости;
- стандартные UNPSC body/hands/watch;
- связанные Skeletons и Blueprint/item assets.

Эти данные нужны для автономного мода и точной посадки часов; одними текстурами из исходного архива выполнить задачу невозможно.

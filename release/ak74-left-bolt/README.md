# AK74 Left Bolt (AK74_LeftBolt_P)

Мод добавляет АК-74 левый обратный хват затвора как у АКМ.

- Скопированы `SCS_Node_41 HS_LeftHand_Slider1` + `SCS_Node_42 HS_GrabLocation_LHSlider1` из АКМ в АК-74
- Добавлены `ChildProperties` `HS_LeftHand_Slider1` и `HS_GrabLocation_LHSlider1` в `BP_AK74_Modular_Base`
- Скелет не трогался (модульные АКМ/АК-74 идентичны), АКС-74У итак имеет 4 слайдера
- Только `BP_AK74_Modular_Base` оверрайдится, остальные АК не трогаются
- Mount `../../../IntoTheRadius2/Content/` — ставить прямо в `IntoTheRadius2/Content/Paks` (как ты ставишь)

Файлы:
- `AK74_LeftBolt_P.utoc` / `.ucas` — ставить в `Paks`
- `BP_AK74_Modular_Base_patched.uasset` — исходный патченый ассет для проверки

Собрано из `BPs.zip` (BPs/Items/Firearms/Primary/AK74/BP_AK74_Modular_Base.uasset 29KB)

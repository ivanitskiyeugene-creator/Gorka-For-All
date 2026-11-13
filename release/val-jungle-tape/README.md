# Val Jungle 40rd BlueTape - Double Magazine (Спарка)

Двойной магазин АС Вал: 2× стандартных 20-патронных магазина, склеенные синей изолентой = 40 патронов.

## Установка

1. **Pak файлы** → `IntoTheRadius2/Content/Paks/`
   - `ValJungle40_BlueTape_P.pak`
   - `ValJungle40_BlueTape_P.utoc` 
   - `ValJungle40_BlueTape_P.ucas`

2. **UE4SS мод** → `IntoTheRadius2/Binaries/Win64/ue4ss/Mods/`
   - Папка `ValJungleMag/` с `Scripts/main.lua`

## Особенности

- **MaxStackSize: 40** (вместо 20) — патч в uasset (offset 0x1CD0), не ломает хедер
- **Визуал: 2× магазина + синяя изолента** — добавляется динамически через UE4SS при спавне магазина:
  - Магазин 1: оригинальная ориентация, смещение -длина/2
  - Магазин 2: повёрнут на 180° (Roll), смещение +длина/2  
  - Изолента: куб в центре, синий материал (#004AAD), имитирует обмотку
- Вес: 36 (стандартный для 20-патронного, 40 патронов в одном слоте)
- Совместимо с существующими сохранениями

## Логи

В `UE4SS.log` ищите:
```
[ValJungleMag] Patched mag 20->40 on <magazine>
[ValJungleMag] Created Mag1 on <magazine>
[ValJungleMag] Created Mag2 on <magazine>
[ValJungleMag] Created Tape on <magazine>
```

## Технические детали

- Контейнер: IoStore TOC v8, несжатый (flags=8)
- Mount point: `../../../IntoTheRadius2/Content/`
- Container ID: `0x79e480e7a0055e2a`
- Патчится ТОЛЬКО `0x1CD0` (MaxStackSize), хедер `0x970/0xC88` не трогаются — избегает краш `0x800001F7`

# Локальное извлечение ассетов Gorka / UNPSC для ITR2

Этот набор нужен, чтобы **не загружать `pakchunk0-Windows.ucas` размером около 13 ГБ**. Скрипт читает на вашем ПК только блоки 57 нужных файлов (28 504 571 байт в распакованном виде) и создаёт небольшой ZIP для отправки.

## Что понадобится

1. Windows 10/11 и установленная текущая Into the Radius 2.
2. Python 3 с сайта <https://www.python.org/downloads/>. При установке оставьте включёнными `py launcher` и/или `Add python.exe to PATH`.
3. Файлы из этого набора в одной папке:
   - `extract_gorka.ps1`;
   - `iostore_extract.py`;
   - `gorka-assets.filters`;
   - этот README.

**pip и дополнительные Python-пакеты не нужны.** Для Oodle скрипт автоматически ищет `oo2core_9_win64.dll` в файлах вашей игры.

## Запуск

1. Распакуйте набор, например в `Documents\gorka-extractor`.
2. Откройте PowerShell в этой папке.
3. Выполните команду, подставив свой путь к `Paks`:

```powershell
powershell -ExecutionPolicy Bypass -File .\extract_gorka.ps1 -Paks "D:\SteamLibrary\steamapps\common\IntoTheRadius2\IntoTheRadius2\Content\Paks"
```

Путь выше только пример. Нужна именно папка, в которой лежат `pakchunk0-Windows.utoc` и `pakchunk0-Windows.ucas`.

Если Python уже настроен, также можно запускать прямо:

```powershell
.\extract_gorka.ps1 -Paks "C:\full\path\to\Paks"
```

Скрипт сам найдёт DLL Oodle, в том числе в папке `Engine` рядом с внутренней папкой `IntoTheRadius2`. Если появится ошибка поиска DLL, укажите её вручную:

```powershell
.\extract_gorka.ps1 -Paks "C:\full\path\to\Paks" -OodleLibrary "C:\full\path\to\oo2core_9_win64.dll"
```

В стандартной установке Steam DLL обычно находится здесь:

```text
IntoTheRadius2\Engine\Binaries\ThirdParty\Oodle\oo2core_9_win64.dll
```

## Что отправить

После строки `SUCCESS` рядом с папкой `gorka-assets` появится:

```text
gorka-assets.zip
```

Загрузите **только этот ZIP** на Google Drive. Ожидается 57 ассетов; при несовпадении скрипт остановится и не выдаст неполный набор за готовый.

**Не загружайте `pakchunk0-Windows.ucas`, `pakchunk0optional-Windows.ucas` и другие многогигабайтные контейнеры.**

Если возникнет ошибка, пришлите её полный текст или скриншот PowerShell. Не меняйте фильтры: вместе с моделями нужны их `.ubulk`, материалы, общий скелет и outfit/bracelet-логика.

# Прогресс

## Лог

### 2026-03-11 — Tester Feedback Module

- **Новый модуль для сбора фидбека от тестеров**:

  ```
  Тестер заполняет форму → TesterFeedback → TesterFeedbackProcessor →
  Task в очереди демона → Автоматическое исполнение
  ```

- **Созданные компоненты**:
  - `core/tester_feedback.py` — Enums, Dataclasses, JSON Storage
  - `core/tester_feedback_processor.py` — конвертация фидбека в Task
  - `web/tester_api.py` — FastAPI router с HTML и JSON endpoints
  - `web/templates/tester/` — формы и страницы (Alpine.js)

- **Типы фидбека**:
  - Баг в игре (с severity: critical/major/minor/cosmetic)
  - Проблема баланса (difficulty/progression/economy/combat)
  - Проблема AI-генерации (интеграция с AssetHistoryManager)

- **Endpoints**:
  - `GET /tester/feedback` — HTML форма
  - `POST /tester/feedback/submit` — отправка формы
  - `GET /tester/feedback/list` — список фидбеков
  - `POST /tester/api/feedback` — JSON API

- **Workflow**: Фидбек → JSON storage → Task с приоритетом по severity → Daemon

### 2026-03-05 — Remote UI Architecture (Split Mode)

- **Split architecture для удалённого доступа к Asset Review**:

  ```
  [Browser] <--WebSocket--> [Remote Server (VPS)] <--WebSocket--> [Local Worker]
                                    |
                              [Static UI]
  ```

- **Компоненты**:
  - `core/ws_protocol.py` — протокол сообщений (команды, ответы, статусы)
  - `core/local_worker.py` — локальный воркер, исполняет команды
  - `web/remote_server.py` — сервер для деплоя, роутит сообщения
  - `web/templates/remote_*.html` — UI для remote режима

- **CLI команды**:
  - `ptero-studio remote-server --port 8081` — запуск на VPS
  - `ptero-studio worker --url ws://vps:8081/ws/worker` — подключение локально

- **Преимущества**:
  - UI доступен из любой точки (хостится на VPS)
  - Генерация остаётся локальной (API ключи не покидают машину)
  - Дизайнер может ревьюить без доступа к коду

### 2026-03-05 — Asset Review System

- **Новая система ревью ассетов** с итеративным фидбэком:

  ```
  manifest.json (planned) → AI генерирует → pending_review →
  Человек смотрит в Web UI → Approve/Reject/Feedback →
  Если Feedback: AI перегенерирует с учётом комментариев
  ```

- **Созданные модули**:
  - `core/asset_feedback.py` — схема фидбэка, история генераций, версионирование
  - `core/asset_scanner.py` — сканирование manifest.json проектов
  - `core/feedback_processor.py` — преобразование фидбэка в промпты
  - `web/templates/review.html` — UI для ревью с формой фидбэка
  - `web/app.py` — endpoints `/review`, `/review/{project}/{category}/{asset_id}`

- **Форма фидбэка включает**:
  - Структурированные проблемы (цвета, композиция, стиль, детали)
  - Свободный текст комментария
  - Интенсивность изменений (минимальные/умеренные/существенные)

- **История версий**:
  - Все генерации сохраняются в `assets/.generations/{asset_id}/v{N}/`
  - Каждая версия: `result.png`, `prompt.txt`, `feedback.json`
  - AI видит всю историю и не повторяет ошибки

- **Протестировано на backpack_hero**:
  - Сгенерированы 4 фона для ресурсных уровней
  - Протестирован цикл: генерация → фидбэк → регенерация v2

### 2026-03-04 — Clean Pixel Art Pipeline + Model Comparison

- **Эксперимент: сравнение AI моделей для img2img стилизации**

  | Модель | Сохраняет размер | Качество | Скорость | Рекомендация |
  |--------|------------------|----------|----------|--------------|
  | **Qwen-edit** | ✅ 100% (1376×768→1376×768) | Хорошо | 26s | **Для UI, точный размер** |
  | **Reve-remix** | ~95% (1376×768→1248×832) | Хорошо | 42s | Альтернатива |
  | **Flux-edit** | Пропорции (1376×768→1024×768) | Хорошо | 69s | Если размер не критичен |
  | Gemini-flash | ❌ Квадрат 1024² | Отлично | Timeout | Нестабилен |
  | Gemini-pro | ❌ Квадрат 1024² | Отлично | 33s | Концепты |
  | GPT-Image-1 | ❌ Генерирует новое | — | — | Только text2img |

- **Clean Pixel Art Pipeline (с сохранением размера)**:

  ```
  Оригинал (любой размер)
        ↓
  ЭТАП 1: Qwen-edit
    Промпт: "clean pixel art, black outlines, flat colors,
             simplified shapes, keep composition"
    Strength: 0.6
        ↓
  ЭТАП 2: Selective Edge Detection
    - Edge detection на результате AI
    - UI маска (исключить текст/панели)
    - Threshold: 30-40
        ↓
  ЭТАП 3: Quantization + Overlay
    - Квантизация 64 цвета
    - Overlay чёрных контуров только на game area
        ↓
  Результат (оригинальный размер сохранён!)
  ```

- **Ключевые выводы**:
  - **Qwen-edit** — единственная модель, сохраняющая 100% оригинальный размер
  - **Gemini** квадратит всё до 1024×1024 (padding workaround возможен, но теряет качество)
  - **Чистые чёрные контуры** требуют AI для упрощения форм + алгоритм для edge detection
  - **UI маскирование** критично — edge detection портит текст

- **Оптимальный pipeline для чистого пиксельарта**:

  ```
  Оригинал
      ↓
  ЭТАП 1: Алгоритмическая квантизация
    - Scale 0.7 → NEAREST upscale
    - Quantize 48 цветов
      ↓
  ЭТАП 2: Qwen-edit с детальным промптом
    Промпт: "Every shape must be ONE SOLID FLAT COLOR:
            triangles, squares, diamonds/rhombuses,
            hexagons, rectangles, all floor tiles.
            Add black 1-pixel outlines.
            NO gradients, NO textures."
    Strength: 0.65
      ↓
  Результат (размер сохранён!)
  ```

- **Важно: Qwen реагирует на конкретные названия форм!**
  - Если не указать "diamonds/rhombuses" — ромбы пола не станут flat
  - Нужно перечислять все типы форм в промпте

- **Сравнение порядка операций**:

  | Pipeline | Flat colors | Контуры | Рекомендация |
  |----------|-------------|---------|--------------|
  | Qwen → Edge detect | ✅ | ✅ Алгоритм | Контроль над контурами |
  | Quantize → Qwen (keep) | ❌ | ⚠️ AI меняет | Не рекомендуется |
  | **Quantize → Qwen (flat)** | ✅ | ✅ AI | **Лучший для flat** |

- **Созданные файлы**:
  - `test_refs/hybrid_step1_qwen.png` — результат Qwen-edit
  - `test_refs/hybrid_selective.png` — финальный результат с контурами
  - `test_refs/quantized_allshapes_qwen.png` — лучший flat результат
  - `test_refs/experiment_*.png` — результаты эксперимента по моделям

### 2026-03-03 (ночь) — Graphics Tool + PixelLab + LoRA Research

- **LoRA Training — облачные варианты** (локальный GPU GTX 1050 Ti 4GB недостаточен):

  | Сервис | Стоимость | Особенности |
  |--------|-----------|-------------|
  | **Civitai Trainer** | 500-2000 Buzz (~$5-20) | Простой UI, интеграция с хабом моделей |
  | **Replicate** | ~$0.50-2/час GPU | API для автоматизации, SDXL LoRA |
  | **TensorArt** | Бесплатно (лимит) | Веб-интерфейс, быстрый старт |
  | **RunPod** | ~$0.40/час A4000 | Полный контроль, Jupyter |
  | **Hugging Face Spaces** | $0.60/час A10G | AutoTrain, интеграция с HF |

  - **AIML API НЕ поддерживает training** — только inference
  - **Рекомендация**: Civitai для старта (10-20 изображений → .safetensors)
  - **Workflow**: Civitai train → Replicate API deploy или локально (если GPU 8GB+)

- **AAA практики в AI графике**:
  - Custom LoRA модели для консистентности стиля
  - ComfyUI + ControlNet pipelines
  - UI валидация: Applitools + Figma

- **Новый инструмент `tools/graphics/`**:
  - Модульная архитектура: generators, transforms, validators, utils
  - `pixellab.py` — полный wrapper для PixelLab API
  - `stylize.py` — стилизация (Deceiver, Loop Hero, clean, retro, game_ui)
  - Документация: `tools/graphics/CLAUDE.md`

- **Протестированные возможности**:
  - Генерация спрайтов с референсом (init_image + strength)
  - Ротации (8 направлений) — AI перерисовывает с правильной перспективой
  - Пикселизация UI с сохранением цветов
  - Стилизация в разных пресетах
  - **Спрайтовые анимации** — 10 пресетов (idle, walk, run, attack, hurt, death...)

- **Модуль `sprite_animation.py`**:
  - `animate_sprite_preset()` — генерация по пресету
  - `generate_character_animations()` — batch генерация набора
  - `create_sprite_gif()` — сборка GIF с масштабированием
  - `create_sprite_sheet()` — сборка sprite sheet
  - Поддержка направлений: north, east, south, west и диагонали
  - Виды камеры: side, low top-down, high top-down

- **PixelLab API интеграция**:
  - API ключ работает с подпиской (баланс $0.00, но генерация бесплатна)
  - Endpoints: `generate-image-pixflux`, `generate-image-bitforge`, `rotate`, `animate-*`, `inpaint`
  - **Лимиты**: pixflux до 400x400, bitforge до 200x200

- **Работа с референсами**:
  - `init_image` + `init_image_strength` (0-100) — img2img подход
  - `style_image` в bitforge — НЕ работает как style transfer (даёт шум)
  - Для копирования стиля: использовать оригинал как `init_image` с strength 60-70%

- **Проблема**: PixelLab генерирует слишком "чистый" пиксель-арт
  - Deceiver/Loop Hero стиль более "грязный" с dithering и текстурой

- **Решение — пайплайн постобработки**:
  ```
  PixelLab (init_image 60-70%)
      ↓
  Пикселизация (resize 50%)
      ↓
  Квантизация (24-32 цвета)
      ↓
  Ordered Dithering (Bayer 4x4)
      ↓
  Десатурация (75-80%)
  ```

- **Создание персонажей в стиле Deceiver**:
  1. Взять существующую картинку Deceiver как `init_image`
  2. `init_image_strength`: 60-70%
  3. Описать НОВОГО персонажа в промпте
  4. Применить постобработку для "грязного" вида

- **UI элементы**:
  - Иконки: 32x32, 64x64 — генерируются отлично
  - Кнопки: 128x48 — работает
  - Панели: 200x200 — идеально для 9-slice
  - Для больших UI — модульный подход (собирать из частей)

- **Файлы эксперимента**: `studio/test_refs/`
  - `wizard_variation.png` — PixelLab генерация
  - `wizard_rough.png` — с постобработкой (ближе к Deceiver)
  - `ui_elements/` — иконки, кнопки, рамки

### 2026-03-03 (вечер)

- **Улучшение Deceiver стилизации**:
  - Исправлена проблема "недостаточно пиксель-арт" — главная причина была `downscale: 1.0`
  - Добавлены готовые пресеты: `loop_hero`, `balanced`, `soft`, `color_only`, `game_ui`, `clean`
  - **Ключевое открытие**: для "честного" пиксель-арта нужен AI этап с промптом про упрощение форм

- **Оптимальный пайплайн для Deceiver стиля**:
  ```
  1. Gemini "clean pixel art, simplified shapes, flat colors" (strength 0.6)
  2. Алгоритм deceiver_style.py --preset game_ui
  ```

- **Новые пресеты**:
  - `game_ui` — для игровых скриншотов (сохраняет читаемость UI)
  - `clean` — без dithering, для результатов AI стилизации

- **Исправления**:
  - Убран внешний хостинг изображений — теперь base64 data URL напрямую
  - Добавлена валидация изображений (`validate_image()`) — защита от битых файлов
  - Fallback хостинги (catbox, litterbox) на случай если понадобятся

- **Выводы по AI моделям**:
  - Gemini понимает "Loop Hero / Deceiver style" и упрощает формы
  - Но обрезает картинки до квадрата (ограничение API)
  - Для сохранения пропорций лучше использовать только первый AI проход + алгоритм

### 2026-03-03

- **Style Transfer Pipeline** (`tools/style_transfer/`):
  - Комбинированный пайплайн: AI img2img + алгоритмическая обработка + UI маска
  - `ai_style_transfer.py` — поддержка 10+ моделей через AIML API
  - `deceiver_style.py` — алгоритмическая стилизация (палитра, dithering)
  - `pipeline.py` — объединяет все этапы
  - `ui_mask.py` — маскирование UI для сохранения читаемости

- **Исследование AI img2img моделей**:
  - **gemini-pro** — 🥇 лучший (сохраняет layout, понимает промпты)
  - **flux-lora-edit** — 🥈 хорош с LoRA пресетами
  - **reve-remix** — 🥉 альтернатива
  - **qwen-edit** — надёжный baseline
  - **flux-kontext** — ❌ объединяет изображения
  - **flux-edit** — ❌ генерирует новое вместо трансформации
  - **Критичный баг исправлен:** `image_urls` (массив) vs `image_url` (строка)

- **LoRA поддержка**:
  - HuggingFace пресеты: `retro-pixel`, `modern-pixel`, `pixel-art-xl`
  - CLI: `--lora-preset retro-pixel` или `--lora-url <url>`

- **Рекомендуемый пайплайн**:
  ```bash
  python pipeline.py input.png output.png --ai-model gemini-pro --ui-mask backpack_hero_minimal
  ```

### 2026-03-02

- **Concept Generator Tool** (`tools/concept_gen/`):
  - Новый модуль для генерации концептов по референсам через AIML API
  - `analyze_reference()` — GPT-4o Vision анализирует референсы (стиль, цвета, настроение)
  - `generate_image()` — Flux/DALL-E генерирует концепты
  - `generate_concepts()` — batch-обработка папки референсов
  - CLI: `python -m tools.concept_gen.generator analyze|generate|quick`
  - Конфиг: `AIMLAPI_KEY` в `config/.env`

- **Исследование моделей для UI генерации**:
  - Протестированы: `flux/schnell`, `flux-pro`, `dall-e-3`
  - **flux/schnell** — быстрый, дешёвый, для итераций
  - **flux-pro** — детальный, понимает UI структуру, читаемый текст
  - **dall-e-3** — не работает через aimlapi (400 error)
  - **Вывод:** flux-pro лучший для UI/интерфейсов

- **UI Layout Workflow для backpack_hero**:
  - Референс: Into the Breach (UI стиль) + backpack_hero (компоновка)
  - Три зоны: Backpack (лево), Mining Field (право-верх), Cave Room (низ)
  - Тёмная схема: #1a1a2e фон, cyan borders, orange accents
  - Сгенерированы 3 финальных варианта V3.2 Dark
  - Результаты: `studio/test_output/v3.2_dark_*.png`

### 2026-02-27

- **Test Plan Generator** (`tools/test_planner.py`):
  - Генерация тест-планов на основе git diff и PROGRESS.md
  - Использует Claude CLI (Opus) — входит в подписку, не API токены
  - CLI: `ptero-studio test-plan <project> [--commits N] [--save]`
  - Dashboard: `/test-plan/{project}` с анимацией загрузки
  - Результат сохраняется в `docs/TEST_PLAN.md`

- **Dashboard Fixes**:
  - ✅ Форма очищается после добавления задачи (`hx-on::after-request`)
  - ✅ IN_PROGRESS задачи не сбрасываются при перезапуске daemon (`--no-reset`)
  - ✅ Секция "Test Plans" с кнопками генерации для каждого проекта

- **Idle Timeout** (`core/daemon.py`):
  - **Проблема:** Фиксированный таймаут 3 мин убивал работающие задачи
  - **Решение:** Idle timeout 90 сек (убивает только если нет вывода)
  - Max timeout 10 мин как safety limit
  - Non-blocking read через threading

- **Markdown Task Inbox** (`core/md_tasks.py`):
  - Импорт задач из markdown файлов
  - CLI: `ptero-studio inbox [--new TITLE]`
  - Папка `tasks_inbox/` для шаблонов и референсов

### 2026-02-23 (session 2)

- **Fix: Claude CLI hanging** (`core/daemon.py`, `core/analyzer.py`):
  - **Проблема:** Задачи висели по 5 минут и таймаутились
  - **Причина:** Claude CLI без `--print` запускался в интерактивном режиме и ждал TTY
  - **Решение:** Добавлен флаг `--print` для non-interactive режима
  - Уменьшен timeout: daemon 5→3 мин, analyzer 2→1 мин

- **Web Dashboard improvements**:
  - Добавлена секция "Running Tasks" с отображением выполняемых задач
  - Elapsed time — показывает сколько времени задача выполняется
  - Progress bar — визуальный индикатор (заполняется за 3 минуты)
  - Auto-refresh каждые 5 секунд через HTMX

- **Opus Analyzer integration** (`core/daemon.py`):
  - Анализатор подключён к daemon (по умолчанию включён)
  - COMPLEX задачи автоматически разбиваются на подзадачи
  - UNCLEAR задачи отклоняются с фидбэком
  - Флаг `--no-analyze` для отключения

- **SQLite Task Queue Refactoring**:
  - Полностью переписан task queue на SQLite (`core/task_db.py`)
  - **Причина:** Multiple Orchestrator/TaskQueue instances causing sync issues
  - **Решение:** Единая SQLite база + WAL mode для concurrent access

  - Новые компоненты:
    - `core/task_db.py` — SQLite-based TaskDB с thread-local connections
    - Atomic `pop()` с UPDATE в одной транзакции
    - `reset_stuck()` для crash recovery (IN_PROGRESS → PENDING)
    - `from_json()` для миграции существующих задач

  - Обновлённые компоненты:
    - `core/daemon.py` — использует TaskDB, встроенная параллельная работа (до 4 workers)
    - `web/app.py` — использует TaskDB напрямую, убраны все `reload()` вызовы
    - `cli.py` — добавлена команда `migrate`, обновлены `tasks` и `add`

  - Устранённые проблемы:
    - ✅ Демон не подхватывал новые задачи (sync issue)
    - ✅ Web dashboard показывал устаревшие данные
    - ✅ Race conditions при параллельном выполнении
    - ✅ Stuck tasks после crash

  - Миграция: `ptero-studio migrate --archive`
    - 36 задач перенесены из JSON в SQLite
    - JSON заархивирован в `tasks.json.bak`

### 2026-02-23

- **Worker Documentation Instructions** (`core/orchestrator.py`):
  - Добавлены явные инструкции для воркеров читать документацию ПЕРЕД началом работы
  - Воркер теперь обязан прочитать: CLAUDE.md, docs/RUNBOOK.md, docs/PROGRESS.md
  - При возникновении проблем — сначала искать решение в документации
  - Если решение не найдено — решить и ЗАПИСАТЬ в документацию
  - **Причина:** воркер игнорировал известные решения (чёрный экран в Pixel Streaming)
  - Обновлён шаблон `config/prompts/worker_isolation.md`

### 2026-02-22 (session 5)
- **Context Isolation** (`core/isolation.py`):
  - IsolationConfig class for loading .isolation files
  - Path validation: boundary check + restricted paths (.git, .env, secrets/)
  - Post-execution validation via git diff
  - Automatic rollback on boundary violations
  - Isolation rules injected into worker prompt
  - Violation logging to studio/logs/violations.jsonl
  - 17 unit tests for isolation

- **Test Suite** (128 tests total, all passing):
  - 82 unit tests (+17 isolation tests)
  - 34 integration tests
  - 12 E2E tests

### 2026-02-22 (session 4)
- **Test Suite** (111 tests total, all passing):
  - 65 unit tests (task_queue, project_status, budget)
  - 34 integration tests (orchestrator, analyzer)
  - 12 E2E tests (full cycle, CLI, parallel execution)
  - `ptero-studio test` command (--unit, --integration, --e2e, --coverage)
  - Thread-safety tests for parallel workers
  - Fixed: e2e tests now use `analyze=False` for mocked tests
  - Fixed: ParallelExecutor tests use class-level patching

- **Inter-project Communication**:
  - `core/project_status.py` — STATUS.json для проектов
  - Состояния: idle, working, blocked, error, ready
  - Автоматическое обновление в orchestrator
  - `ptero-studio status --projects` для обзора всех проектов

- **Parallel Workers**:
  - `core/parallel.py` — параллельное выполнение задач
  - Thread-safe task queue с project locking
  - `--workers N` (1-4) для daemon команды
  - Разные проекты выполняются параллельно, один проект — последовательно

- **File Logging**:
  - `core/logging_config.py` — настройка логирования
  - `logs/daemon.log` — общий лог демона (daily rotation, 7 дней)
  - `logs/tasks.log` — детальный лог задач
  - Флаг `--no-log` для отключения файлового логирования

### 2026-02-22 (session 3)
- **Opus Analyzer Pipeline**:
  - `core/analyzer.py` — анализ задач через Opus перед выполнением
  - Классификация: SIMPLE, CLEAR, COMPLEX, UNCLEAR
  - COMPLEX → автоматическая декомпозиция на подзадачи
  - UNCLEAR → отклонение с фидбэком пользователю
  - Флаг `--no-analyze` для пропуска анализа

- **Улучшенный промпт**:
  - Контекст про игровые объекты (уровень = локация, не меню)
  - Рекомендуемые файлы для чтения
  - Поддержка `--model` для выбора модели

- **Тест на реальной задаче**:
  - "добавить парк с деревьями" → Opus декомпозировал на 7 подзадач
  - "сделай интереснее" → Opus отклонил как UNCLEAR
  - Создан park_room.lua, rooms.lua, система переходов
  - Игра работает с новым контентом

- **Статистика сессии**:
  - 19 задач выполнено
  - 2 задачи отклонены (UNCLEAR)
  - $0.08 потрачено

### 2026-02-22 (session 2)
- **MVP готов и протестирован**:
  - Полный цикл: idea → decompose → daemon → validate → budget
  - Тест на hamster: добавлен loading screen через 3 автоматические задачи

- **Daemon mode** (`ptero-studio daemon`):
  - Непрерывное выполнение задач из очереди
  - Опции: --max, --interval, --max-failures
  - Graceful shutdown по Ctrl+C

- **Budget tracking** (`ptero-studio budget`):
  - Подсчёт токенов и стоимости
  - Дневные и месячные лимиты
  - Интеграция с orchestrator

- **Декомпозиция идей** (`ptero-studio idea`):
  - Разбивка идей на конкретные задачи через Claude Code
  - --dry-run для просмотра без добавления
  - --max-tasks для ограничения

- **Unreal интеграция**:
  - Проекты автоматически обнаруживаются
  - Валидация через window capture (если редактор открыт)

- **Валидация для LÖVE**:
  - Background capture работает (PrintWindow API)
  - Скриншоты сохраняются в `studio/validation/`

### 2025-02-22
- **Реализован Toolbox (Фаза 0)**:
  - `tools/window_capture/` — захват окон через Windows API
  - `tools/vision_validator/` — проверка через Claude Vision API
  - `tools/game_runner/` — запуск LÖVE/Unreal проектов
  - `tools/cli.py` — единая точка входа `ptero-tool`
- **Реализован Core Infrastructure (Фаза 1)**:
  - `core/project.py` — модель проекта с discover и scaffold
  - `core/task_queue.py` — приоритетная очередь задач (JSON persistence)
  - `core/orchestrator.py` — координатор (проекты + задачи + выполнение через Claude Code)
  - `cli.py` — CLI `ptero-studio` (projects, tasks, add, run, new, status)
- **Протестирован полный цикл**: add → run → Claude Code выполняет → коммит
- Ключевое открытие: stdin без `-p` включает tool execution в Claude CLI
- Создан `pyproject.toml`

### 2025-02-21 (session 2)
- Добавлена архитектура Toolbox — инструменты как отдельные модули
- Добавлена архитектура Inter-project Communication (STATUS.json)
- Добавлена архитектура Context Isolation (многоуровневая защита)
- Создана структура tools/ с документацией для 3 инструментов
- Создан шаблон isolation.yaml для границ проектов
- Создан системный промпт worker_isolation.md (EN) для изоляции агентов
- Добавлены фазы 0, 0.5, 0.6 в план реализации
- Добавлена секция Task Decomposition с decision tree
- Добавлена секция Git Strategy (multi-repo)
- Инициализирован git репозиторий для studio/
- Создан .gitignore для workspace и studio

### 2025-02-21 (session 1)
- Создана структура документации Ptero Dactyl Studio
- Написана архитектура системы (Orchestrator, Adapters, Validation)
- Определены 7 фаз реализации
- Интегрированы существующие наработки:
  - babylon/MCP → UnrealAdapter
  - backpack_hero → тестовый полигон для LoveAdapter
  - studio/README.md → основа для CLI

## Бенчмарки

### Базовые метрики

| Метрика | Значение | Дата | Контекст |
|---------|----------|------|----------|
| babylon MCP tools | 28 | 2025-02-21 | Готовы к интеграции |
| backpack_hero LOC | ~18,600 | 2025-02-21 | Тестовый проект |
| Token cost (Vision 800x600) | 640 tokens | 2025-02-21 | Из babylon docs |

### История измерений

<!-- Шаблон:
### YYYY-MM-DD — [Что изменилось]
**До:** ...
**После:** ...
**Вывод:** ...
-->

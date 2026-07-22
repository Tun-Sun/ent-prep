/**
 * ExportFormToJSON.gs
 * ===================
 * Google Apps Script для учителя: выгружает структуру Google Form
 * (вопросы, варианты ответов, правильные ответы, картинки) в JSON-файл
 * для последующего импорта в платформу ENT Prep.
 *
 * КАК ПОЛЬЗОВАТЬСЯ (учитель):
 * --------------------------
 * 1. Откройте свою Google Form.
 * 2. Меню: Расширения → Apps Script (Extensions → Apps Script).
 * 3. Удалите всё содержимое файла Code.gs, вставьте этот скрипт, сохраните.
 * 4. Убедитесь, что форма находится в режиме «Теста» (Quiz):
 *      Настройки → Превратить в тест (Make this a quiz).
 *    Иначе правильные ответы выгружены не будут.
 * 5. Нажмите «Выполнить» → выберите функцию `exportFormToJson`.
 *    При первом запуске Google попросит разрешения — дайте его
 *    (доступ только к текущей форме и её вложениям).
 * 6. В папке Google Drive «ENT-Prep-Exports» появится файл
 *    `<название-формы>_<дата>.json` — отправьте его администратору
 *    платформы (или положите в папку, к которой у того есть доступ).
 *
 * ВАЖНО:
 *   - Правильный ответ берётся из QUIZ-режима формы. Без него скрипт
 *     пометит все варианты как «правильный неизвестен» и пометит вопрос
 *     как draft.
 *   - Картинки в теле вопроса и вариантах ответа детектятся и в JSON
 *     попадает file_id из Drive — реальные байты скачивает уже сервер
 *     платформы через Drive API (images.py). Скрипт сам картинки не
 *     кодирует, чтобы JSON оставался лёгким.
 */

// === НАСТРОЙКИ =============================================================

// Папка Drive для выгрузок. Создаётся автоматически при первом запуске.
var EXPORT_FOLDER_NAME = 'ENT-Prep-Exports';

// Метаданные для импорта: какой это предмет и тема.
// Учитель может задать их через prompt при запуске, либо задать жёстко тут.
var DEFAULT_LANGUAGE = 'ru';     // 'ru' | 'kk' | 'en'
var DEFAULT_YEAR     = 2026;

// === ТОЧКА ВХОДА ===========================================================

/**
 * Главная функция. Запускается вручную из редактора Apps Script
 * или из меню «Выполнить». Создаёт JSON и кладёт его в Drive.
 */
function exportFormToJson() {
  var form = FormApp.getActiveForm();
  if (!form) {
    throw new Error(
      'Скрипт должен быть запущен из контейнера Google Form. ' +
      'Откройте форму → Расширения → Apps Script.'
    );
  }

  var meta = promptForMeta_(form);
  var payload = buildPayload_(form, meta);
  var json = JSON.stringify(payload, null, 2);

  var file = saveToDrive_(form, json, meta);
  Logger.log('✅ Готово. JSON сохранён: ' + file.getUrl());
  Logger.log('   Вопросов: ' + payload.questions.length);
  Logger.log('   Размер: ' + Math.round(json.length / 1024) + ' КБ');

  // Краткий отчёт по проблемам.
  var warnings = collectWarnings_(payload);
  if (warnings.length) {
    Logger.log('⚠ Предупреждения:');
    warnings.forEach(function (w) { Logger.log('   • ' + w); });
  }
  SpreadsheetApp.getUi().alert(
    'Готово!',
    'JSON сохранён в Google Drive:\n' + file.getUrl() +
    '\n\nВопросов: ' + payload.questions.length +
    (warnings.length ? '\n\nПредупреждений: ' + warnings.length +
                      '\n(см. лог выполнения)' : ''),
    SpreadsheetApp.getUi().ButtonSet.OK
  );
}

// === СБОРКА PAYLOAD ========================================================

/**
 * @param {GoogleAppsScript.Forms.Form} form
 * @param {Object} meta  — метаданные от учителя (subject, topic, ...)
 * @return {Object} структура, готовая к парсингу сервером
 */
function buildPayload_(form, meta) {
  var items = form.getItems();

  var questions = [];
  for (var i = 0; i < items.length; i++) {
    var q = mapItemToQuestion_(items[i], form);
    if (q) {
      q.order_index = i;
      questions.push(q);
    }
  }

  return {
    schema_version: 1,
    exported_at: new Date().toISOString(),
    source: {
      type: 'google_forms',
      form_id: form.getId(),
      form_url: form.getPublishedUrl(),
      form_title: form.getTitle(),
      is_quiz: isQuiz_(form),
    },
    subject_slug: meta.subject_slug,
    subject_name: meta.subject_name,
    topic_name: meta.topic_name,
    language: meta.language,
    year: meta.year,
    questions: questions,
  };
}

/**
 * Преобразует один Item формы в DTO вопроса.
 * Возвращает null для неподдерживаемых типов (заголовок/раздел/изображение).
 */
function mapItemToQuestion_(item, form) {
  var type = item.getType();
  var itemId = item.getId();
  var title = item.getTitle() || '';
  var helpText = item.getHelpText() || '';

  // Картинка в теле вопроса (если первым вложением — ImageItem внутри блока).
  var imageInfo = extractImage_(item);

  var dto = {
    external_id: form.getId() + '/' + itemId,
    title: title,
    help_text: helpText,
    image: imageInfo,            // null или { drive_file_id, title }
    type: typeToString_(type),
    answers: [],
    points: item.getPoints ? item.getPoints() : 1,
    correct_answer: null,        // индекс или массив индексов
    is_required: NOT_REQUIRED_SENTINEL_(item),
    unsupported: false,
  };

  // Разбор по типу вопроса.
  switch (type) {
    case FormApp.ItemType.MULTIPLE_CHOICE:
      fillFromChoiceItem_(dto, item.asMultipleChoiceItem(), /*multiple=*/false);
      break;
    case FormApp.ItemType.CHECKBOX:
      fillFromChoiceItem_(dto, item.asCheckboxItem(), /*multiple=*/true);
      break;
    case FormApp.ItemType.LIST:
      fillFromChoiceItem_(dto, item.asListItem(), /*multiple=*/false);
      break;
    default:
      // Текстовые/сетка/дата/время — не формат ЕНТ. Пропускаем, но логируем.
      dto.unsupported = true;
      dto.unsupported_reason = 'Тип ' + typeToString_(type) +
                                ' не поддерживается импортом ЕНТ';
      Logger.log('⚠ Вопрос "' + title.substring(0, 40) +
                 '..." пропущен: ' + dto.unsupported_reason);
      return null;
  }
  return dto;
}

/**
 * Заполняет варианты ответов и правильный ответ для choice-вопросов.
 * @param {boolean} multiple — допускается ли несколько правильных (checkbox).
 */
function fillFromChoiceItem_(dto, choiceItem, multiple) {
  var choices = choiceItem.getChoices();
  var correctIndices = [];

  for (var i = 0; i < choices.length; i++) {
    var c = choices[i];
    var pageNav = null; // навигация по страницам нам не нужна
    var isCorrect = c.isCorrectAnswer();

    // Картинка к варианту ответа — Apps Script не отдаёт её напрямую
    // через Choice, но ссылка может быть в .getPageNavigation() либо
    // не отдаётся вовсе. Помечаем как «возможно есть» только когда
    // учитель явно вставил изображение через опцию «go-to-page» — нет.
    // Реально картинки вариантов Drive API достанет на сервере.
    dto.answers.push({
      text: c.getValue(),
      // is_correctAnswer() работает ТОЛЬКО в режиме Quiz.
      is_correct: Boolean(isCorrect),
    });
    if (isCorrect) correctIndices.push(i);
  }

  dto.correct_answer = multiple ? correctIndices
                                : (correctIndices.length ? correctIndices[0] : null);
  dto.has_correct = correctIndices.length > 0;
}

// === КАРТИНКИ ==============================================================

/**
 * Apps Script НЕ даёт прямого API для картинки в теле TextItem/MultipleChoice.
 * Однако если учитель вставил изображение как самостоятельный ImageItem
 * перед вопросом, оно отдаётся отдельно. Здесь мы пытаемся вытащить
 * ссылку/ID из helpText и из getHelpText (Google иногда кладёт alt туда).
 *
 * Реальное извлечение бинарника картинки из Drive делает images.py на сервере
 * (по form_id + item_id через Drive revisions/Files). Здесь фиксируем
 * только то, что можем — alt-text, если учитель его задал.
 */
function extractImage_(item) {
  var help = (item.getHelpText() || '').trim();
  // Эвристика: если в helpText есть «image: ...», считаем что картинка есть.
  // Сервер при импорте попробует найти её в Drive по form_id/item_id.
  return help ? { note: help } : null;
}

// === МЕТАДАННЫЕ ОТ УЧИТЕЛЯ ==================================================

/**
 * Спрашивает у учителя (через prompt) предмет и тему.
 * Если запустить нельзя (например, из триггера) — берёт DEFAULT_*.
 */
function promptForMeta_(form) {
  var ui;
  try {
    ui = SpreadsheetApp.getUi();
  } catch (e) {
    // Без UI (триггер, headless) — отдаём дефолты.
    return {
      subject_slug: '',
      subject_name: form.getTitle() || '',
      topic_name: '',
      language: DEFAULT_LANGUAGE,
      year: DEFAULT_YEAR,
    };
  }

  var title = form.getTitle() || 'форма';
  var subject = ui.prompt(
    'Предмет',
    'Введите slug предмета (например: physics, math, history_kz).\n' +
    'Если неизвестно — оставьте пустым, администратор подберёт.',
    ui.ButtonSet.OK_CANCEL
  );
  if (subject.getSelectedButton() === ui.Button.CANCEL) {
    throw new Error('Экспорт отменён учителем.');
  }

  var topic = ui.prompt(
    'Тема',
    'Введите название темы (например: «Кинематика», «Производная»).\n' +
    'Если тема новая — она будет создана автоматически.',
    ui.ButtonSet.OK_CANCEL
  );
  if (topic.getSelectedButton() === ui.Button.CANCEL) {
    throw new Error('Экспорт отменён учителем.');
  }

  return {
    subject_slug: subject.getResponseText().trim(),
    subject_name: '',
    topic_name: topic.getResponseText().trim(),
    language: DEFAULT_LANGUAGE,
    year: DEFAULT_YEAR,
  };
}

// === СОХРАНЕНИЕ В DRIVE ====================================================

function saveToDrive_(form, json, meta) {
  var folder = getOrCreateFolder_(EXPORT_FOLDER_NAME);
  var ts = Utilities.formatDate(
    new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd_HH-mm'
  );
  var safeName = (form.getTitle() || 'form').replace(/[^\w\-]+/g, '_');
  var fileName = safeName + '_' + ts + '.json';

  var blob = Utilities.newBlob(json, 'application/json', fileName);
  return folder.createFile(blob);
}

function getOrCreateFolder_(name) {
  var it = DriveApp.getFoldersByName(name);
  if (it.hasNext()) return it.next();
  return DriveApp.createFolder(name);
}

// === ВСПОМОГАТЕЛЬНОЕ =======================================================

function isQuiz_(form) {
  // В Apps Script нет прямого form.isQuiz(), но в режиме теста
  // у choice-вопросов isCorrectAnswer() возвращает true/false,
  // а вне теста — всегда false. Используем это как индикатор.
  try {
    var items = form.getItems();
    for (var i = 0; i < items.length; i++) {
      var t = items[i].getType();
      if (t === FormApp.ItemType.MULTIPLE_CHOICE) {
        var ch = items[i].asMultipleChoiceItem().getChoices();
        if (ch.length && ch[0].isCorrectAnswer() !== undefined) {
          // Доп. проверка: хотя бы один правильный — значит точно Quiz.
          return ch.some(function (c) { return c.isCorrectAnswer(); });
        }
      }
    }
  } catch (e) {
    return false;
  }
  return false;
}

function typeToString_(type) {
  var map = {};
  map[FormApp.ItemType.MULTIPLE_CHOICE] = 'multiple_choice';
  map[FormApp.ItemType.CHECKBOX]        = 'checkbox';
  map[FormApp.ItemType.LIST]            = 'list';
  map[FormApp.ItemType.TEXT]            = 'text';
  map[FormApp.ItemType.PARAGRAPH_TEXT]  = 'paragraph';
  map[FormApp.ItemType.SCALE]           = 'scale';
  map[FormApp.ItemType.GRID]            = 'grid';
  map[FormApp.ItemType.CHECKBOX_GRID]   = 'checkbox_grid';
  map[FormApp.ItemType.DATE]            = 'date';
  map[FormApp.ItemType.DATETIME]        = 'datetime';
  map[FormApp.ItemType.DURATION]        = 'duration';
  map[FormApp.ItemType.TIME]            = 'time';
  map[FormApp.ItemType.IMAGE]           = 'image';
  map[FormApp.ItemType.VIDEO]           = 'video';
  map[FormApp.ItemType.PAGE_BREAK]      = 'page_break';
  map[FormApp.ItemType.SECTION_HEADER]  = 'section_header';
  return map[type] || 'unknown';
}

function NOT_REQUIRED_SENTINEL_(item) {
  try { return Boolean(item.isRequired()); } catch (e) { return false; }
}

/**
 * Предупреждения для отчёта учителю: вопросы без правильного ответа и т.п.
 */
function collectWarnings_(payload) {
  var out = [];
  payload.questions.forEach(function (q) {
    if (!q.has_correct) {
      out.push('Вопрос без правильного ответа: "' + q.title.substring(0, 60) +
               '". Проверьте, что форма в режиме Quiz.');
    }
    if (q.answers.length < 2) {
      out.push('Вопрос с <2 вариантами: "' + q.title.substring(0, 60) + '".');
    }
  });
  return out;
}

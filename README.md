# Local Ollama Agent

![Dashboard Preview](docs/assets/dashboard-shot.svg)

وكيل محلي مبني فوق `Ollama` مع:

- Router بين نموذج الكود والرؤية
- ذاكرة قصيرة وطويلة في `sqlite`
- RAG محلي على ملفات مجلد `knowledge/`
- أدوات آمنة للقراءة والبحث وتعديل نصي محدود
- أوضاع تشغيل جاهزة: عام، مبرمج، رؤية، مدير مشروع
- Planner للمهام الطويلة
- Task runs محفوظة مع تقدّم وخطوات مرئية داخل الواجهة
- واجهة ويب محلية تدعم النصوص والصور
- Telemetry بسيط لقياس التشغيل
- Hybrid RAG: embeddings عند توفرها مع fallback معجمي
- مستويات صلاحيات للأدوات: `auto`, `none`, `local-read`, `local-write`, `internet-read`, `internet-download`, `full`
- قوالب مشاريع جاهزة يمكن إنشاؤها مباشرة داخل مساحة العمل
- قائمة محادثات حديثة داخل الواجهة
- حفظ إعدادات محلية من الواجهة
- تصدير/استيراد المحادثات بصيغة JSON
- بناء مشروع كامل داخل مجلد هدف محدد مع `project_spec.json`
- pipeline تنفيذ: `install / run / smoke test / auto-fix notes`
- أدوات إنترنت: بحث ويب، جلب صفحات، جلب JSON، وتنزيل ملفات
- مجلد `downloads/` مع فهرسة تلقائية للمحتوى النصي المنزّل داخل RAG
- صلاحيات مستقلة للإنترنت والملفات المحلية
- background jobs للعمليات الطويلة
- API key اختياري لحماية نقاط الـ API
- مزود بحث قابل للتبديل مع allowlist للنطاقات

## التشغيل

```bash
python3 run.py
```

ثم افتح:

```text
http://127.0.0.1:8765
```

## تكامل M1 المحلي

لـ `MacBook Pro M1/M2/M3/M4` أصبح المشروع مضبوطًا افتراضيًا ليعمل مع:

- `Ollama Native` على:
  - `http://127.0.0.1:11434`
- `SearXNG` المحلي على:
  - `http://127.0.0.1:8080`

إذا كانت البيئة المحلية تعمل، فالمشروع سيستخدمها مباشرة بدون أي تعديل إضافي.

أوامر سريعة:

```bash
make m1-stack-up
make m1-stack-down
```

أو مباشرة:

```bash
zsh deploy/m1-open-webui/start-stack.sh
zsh deploy/m1-open-webui/stop-stack.sh
```

ويوجد مثال متغيرات بيئة جاهز هنا:

```text
.env.m1-local.example
```

## المتطلبات

- `Ollama` يعمل محلياً على `http://127.0.0.1:11434`
- النماذج الافتراضية:
  - `qwen2.5-coder:7b`
  - `qwen2.5vl:latest`

## تخصيص النماذج

يمكن تغييرها بمتغيرات البيئة:

```bash
DEFAULT_CHAT_MODEL=qwen2.5-coder:7b
CODE_MODEL=qwen2.5-coder:7b
VISION_MODEL=qwen2.5vl:latest
EMBEDDING_MODEL=nomic-embed-text
DEFAULT_AGENT_MODE=general
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

## المعرفة المحلية

ضع ملفاتك النصية داخل:

```text
knowledge/
```

ثم اضغط "إعادة فهرسة المعرفة" من الواجهة.

## الأمان

- الأدوات المحلية والإنترنت تعمل حسب مستوى الصلاحية المختار:
  - `auto`
  - `none`
  - `local-read`
  - `local-write`
  - `internet-read`
  - `internet-download`
  - `full`
- الوضع الافتراضي هو `auto`:
  - يسمح للوكيل تلقائياً بقراءة ملفات المشروع
  - ويتيح البحث والجلب والتنزيل من الإنترنت
  - ويمنع الكتابة المحلية حتى ترفع الصلاحية عمداً
- أوامر shell محصورة في قائمة آمنة للقراءة فقط.
- الوصول إلى الملفات محصور داخل مساحة العمل الحالية.
- إذا كان نموذج embedding غير متوفر، يعود البحث تلقائياً إلى الفهرسة المعجمية.
- كل محادثة يمكن أن تنتج `workflow run` محفوظاً في قاعدة البيانات مع خطوات ومخرجات.

## الإنترنت والتنزيلات

- المحتوى المنزّل يُحفظ داخل:

```text
downloads/
```

- الملفات النصية و`html/json/xml/csv` المنزلة تُحوّل تلقائياً إلى نص قابل للفهرسة.
- يمكن للوكيل استخدام أدوات:
  - `web_search`
  - `fetch_url`
  - `web_fetch`
  - `fetch_json`
  - `download_file`
- `web_search` يعمل الآن بتسلسل ذكي:
  - `Ollama Web Search API` أولاً إذا كان `OLLAMA_API_KEY` مضبوطاً
  - ثم `SearXNG` إذا كان `SEARCH_BASE_URL` موجوداً
  - ثم fallback أخير إلى `DuckDuckGo HTML`
- الوكيل يستخدم الآن `Ollama tool calling` الرسمي داخل `/api/chat`، مع fallback متوافق إلى البروتوكول النصي القديم فقط عند الحاجة.
- كل نتيجة بحث أو جلب ويب تعود بصيغة منظمة تحتوي:
  - `provider_used`
  - `fallback_used`
  - `citations`
- وعند استخدام أدوات الويب داخل المحادثة يحاول الوكيل توليد `ملخص منظّم` عبر structured outputs فوق نفس النتائج.

متغيرات البيئة ذات الصلة:

```bash
INTERNET_ENABLED=true
MAX_DOWNLOAD_SIZE_MB=10
SEARCH_PROVIDER=auto
SEARCH_BASE_URL=http://127.0.0.1:8080
OLLAMA_API_KEY=
OLLAMA_WEB_BASE_URL=https://ollama.com
ALLOWED_DOMAINS=
```

إذا أردت تفعيل `SearXNG` كـ fallback أو كمزود مباشر:

```bash
SEARCH_PROVIDER=searxng
SEARCH_BASE_URL=http://127.0.0.1:8080
```

إذا أردت الاعتماد على بحث Ollama الرسمي أولاً:

```bash
SEARCH_PROVIDER=auto
OLLAMA_API_KEY=sk-...
```

## Background Jobs

العمليات الطويلة مثل:
- `Build Full Project`
- `Execute Project`

يمكن تشغيلها في الخلفية من الواجهة. كما توجد endpoints داخلية لقراءة حالة job:

```text
GET /api/jobs/<job_id>
```

## API Security

يمكن حماية الـ API بمفتاح اختياري:

```bash
AGENT_API_KEY=your-secret-key
```

وعند تفعيله يجب تمرير:

```text
X-API-Key: your-secret-key
```

## القوالب الجاهزة

- `python-api`
- `web-starter`
- `flask-api`
- `fastapi-api`
- `node-api`
- `react-starter`

يمكن إنشاؤها من داخل الواجهة في مجلدات مثل `generated/python-api`.

## Build Full Project

يمكنك الآن:
- كتابة وصف المشروع
- تحديد `Target Directory`
- اختيار السماح بمجلد خارج مساحة العمل عند الحاجة

ثم سيقوم الوكيل بإنشاء:
- scaffold أولي
- `project_spec.json`
- `NEXT_STEPS.md`
- أوامر `install / run / test`

## Landing Page

يوجد Landing بسيطة داخل:

```text
docs/index.html
```

وتعرض لمحة بصرية عن:
- الواجهة
- بناء المشاريع
- تتبع الـ workflows

## Screenshots

### Builder

![Builder Screenshot](docs/assets/builder-shot.svg)

### Workflow Tracking

![Workflow Screenshot](docs/assets/workflow-shot.svg)

## Release v1.0.0

ملاحظات الإصدار موجودة في:

```text
RELEASE_NOTES_v1.0.0.md
```

## Execute Project

بعد إنشاء المشروع يمكنك الآن من الواجهة:
- تثبيت الاعتماديات
- تشغيل المشروع
- تنفيذ smoke test
- الحصول على `AUTO_FIX_NOTES.md` عند الفشل الأولي

مهم:
- التنفيذ يعتمد على الأدوات والاعتماديات المتوفرة في جهازك
- التثبيت قد يفشل إذا كانت الحزم غير متاحة أو الشبكة غير مسموحة

## التشغيل كخدمة

تشغيل محلي مباشر:

```bash
make run
```

تشغيل الاختبارات:

```bash
make test
```

تشغيل عبر Docker:

```bash
docker compose up --build
```

ثم افتح:

```text
http://127.0.0.1:8765
```

ملاحظة:
- الحاوية تتصل بـ `Ollama` على الجهاز المضيف عبر `host.docker.internal:11434`.
- ما زلت تحتاج أن يكون `Ollama.app` أو الخادم المحلي شغالاً خارج الحاوية.

## تهيئة المستودع

تم تجهيز المشروع ليرتبط بسهولة بمستودع Git:

```bash
git init
git add .
git commit -m "Initial local agent"
```

إذا أردت ربطه بمستودع بعيد لاحقاً:

```bash
git remote add origin <your-repo-url>
git branch -M main
git push -u origin main
```

## CI

يوجد ملف GitHub Actions في:

```text
.github/workflows/ci.yml
```

وهو يشغّل:
- `py_compile`
- اختبارات `unittest`

## ملاحظات

- هذا MVP عملي، وليس منصة إنتاجية كاملة.
- إذا كان `ollama` من الطرفية ينهار عندك لكن `Ollama.app` يعمل، فالواجهة ستتصل مباشرة بالـ HTTP API المحلي دون الاعتماد على CLI.

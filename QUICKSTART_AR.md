# دليل تشغيل سريع

هذا أقصر مسار لتشغيل المشروع على جهازك الحالي:

## 1. شغّل البيئة المحلية

```bash
cd /Users/alhade/Desktop/786
make m1-stack-up
```

هذا الأمر يشغّل:

- `Ollama Native` على `127.0.0.1:11434`
- `Open WebUI` على `localhost:3000`
- `SearXNG` على `localhost:8080`

## 2. شغّل مشروع 786

افتح طرفية ثانية:

```bash
cd /Users/alhade/Desktop/786
python3 run.py
```

## 3. افتح الواجهات

- مشروعك: [http://127.0.0.1:8765](http://127.0.0.1:8765)
- Open WebUI: [http://localhost:3000](http://localhost:3000)
- SearXNG: [http://localhost:8080](http://localhost:8080)

## 4. تأكد أن Ollama يعمل

```bash
curl http://127.0.0.1:11434/api/version
ollama list
```

## 5. عند الانتهاء

```bash
cd /Users/alhade/Desktop/786
make m1-stack-down
```

## ملاحظات مهمة

- الوضع الافتراضي داخل مشروع `786` هو `auto`
- هذا يعني أن الوكيل يستطيع تلقائيًا:
  - قراءة الملفات
  - البحث من الإنترنت
  - جلب الصفحات
  - تنزيل الملفات
- إذا أردت السماح له بالكتابة داخل المشروع، ارفع الصلاحية إلى `local-write` أو `full`

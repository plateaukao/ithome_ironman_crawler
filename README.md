1. After running the script, a combined.html will be created.
2. Use browser to open it, and save it as complete html: a html will be created with a folder for all the resources.
3. Use Calibre's ebook-convert with following command:
   
```convert saved_file.html output.epub --level1-toc="//h:h2[re:test(@class, "qa-header__title", "i")]" --output-profile tablet```

(`--output-profile tablet` is used to prevent from rescaling images in html)

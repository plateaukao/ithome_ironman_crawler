# iThome Ironman Book creator

## Prerequisites
* Python 3
* `pip install requests beautifulsoup4 Pillow ebooklib simple-term-menu`

## Usage

### Interactive mode (no arguments)

```
python fetch_as_single_html.py
```

Browse award-winning series from 2020-2025 via arrow-key menus:

1. Select a year
2. Select an award tier (冠軍 / 優選 / 佳作 / 佛心分享)
3. Select a series (shown with category)
4. Enter output filename

### Command-line mode

```
python fetch_as_single_html.py <series_url> [output_filename.epub]
```

Example:
```
python fetch_as_single_html.py https://ithelp.ithome.com.tw/users/20112126/ironman/2841 deep_learning.epub
```

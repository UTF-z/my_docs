<style type="text/css">
    h1 { counter-reset: h2counter; }
    h2 { counter-reset: h3counter; }
    h3 { counter-reset: h4counter; }
    h4 { counter-reset: h5counter; }
    h5 { counter-reset: h6counter; }
    h6 { }
    h2::before {
      counter-increment: h2counter;
      content: counter(h2counter) ".\0000a0\0000a0";
    }
    h3::before {
      counter-increment: h3counter;
      content: counter(h2counter) "."
                counter(h3counter) ".\0000a0\0000a0";
    }
    h4::before {
      counter-increment: h4counter;
      content: counter(h2counter) "."
                counter(h3counter) "."
                counter(h4counter) ".\0000a0\0000a0";
    }
    h5::before {
      counter-increment: h5counter;
      content: counter(h2counter) "."
                counter(h3counter) "."
                counter(h4counter) "."
                counter(h5counter) ".\0000a0\0000a0";
    }
    h6::before {
      counter-increment: h6counter;
      content: counter(h2counter) "."
                counter(h3counter) "."
                counter(h4counter) "."
                counter(h5counter) "."
                counter(h6counter) ".\0000a0\0000a0";
    }
</style>

# HTML 语法基础

## HTML 基本格式
```html
<!doctype html>
<html lang="zh-CN"> <!-- 声明文档主语言，用于SEO以及无障碍 -->
    <head>
        <title>标题</title>
        <meta/>
        <link/>
        <script><script/>
    </head>
    <body>
        <p>段落</p>
    </body>
</html>
```

## 头部
头部包含了title，meta，link，script等字段，一般不会被渲染。
- title：网页标题
    这个是一个字符串，浏览器会显示在标签栏中，在搜索引擎中也可能会被搜索到。它和页面中的`<h1>`不一样，不会被渲染为页面的一部分。
- meta: 元数据
    元数据是关于数据的数据，比如说字符集，描述，关键字，作者，等等。
    元数据的格式如下：
    ```html
    <meta charset="utf-8"/>
    <meta name="author" content="Junming"/>
    <meta name="description" content="免费 Web 开发教程"/>
    ```
    某些网站，比如Facebook，Twitter等拥有自己的元数据协议。以下是Facebook的元数据协议Open Graph Data，效果是，当你在 Facebook 上链接到 MDN Web 文档时，该链接将显示一个图像和描述：这为用户提供更丰富的体验：
    ```html
    <meta
        property="og:image"
        content="URL_ADDRESS"
    />
    <meta
        property="og:description"
        content="DESCRIPTION_TEXT"
    />
    <meta
        property="og:title"
        content="TITLE_TEXT"
    />
    ```
- link: 链接
    链接是用来引用外部资源的，比如说CSS，字体，图标，等等。
    链接的格式如下：
    ```html
    <link rel="stylesheet" href="style.css"/>
    <link rel="icon" sizes="114x114" href="favicon.ico"/>
    ```
- script: 脚本
    Javascript脚本是用来定义动态交互行为的。注意它不是一个空元素，它是一个容器，用来包含脚本代码。也可以通过src属性引用外部脚本。
    脚本的格式如下：
    ```html
    <script src="script.js" defer></script>
    ```
    defer属性表示脚本在文档完全被解析和显示之后再执行。

## 文本处理
- 标题
    标题是用来定义页面结构的，它有六级，从`<h1>`到`<h6>`。
    标题的格式如下：
    ```html
    <h1>一级标题</h1>
    <h2>二级标题</h2>
    ```
- 段落
    段落是用来定义文本内容的，它是一个块级元素，会自动换行。
    段落的格式如下：
    ```html
    <p>这是一个段落。</p>
    ```
- 换行符
    换行符是用来换行的，它是一个空元素，没有内容。它和段落不同，换行之后没有间隙。
    换行符的格式如下：
    ```html
    <br/>
    ```
- 水平线
    水平线是用来定义分隔线的，它是一个空元素，没有内容。
    水平线的格式如下：
    ```html
    <hr/>
    ```
- 强调
    强调是用来定义强调的，它是一个行内元素，一般包围文字，有加粗，斜体，下划线，等等。
    强调的格式如下：
    ```html
    <em>强调</em>
    <strong>加粗</strong>
    <u>下划线</u>
    ```
- 列表
    列表是用来定义列表的，它有三种类型：无序列表，有序列表，定义列表。
    无序列表的格式如下：
    ```html
    <ul>
        <li>列表项</li>
    </ul>
    ```
    有序列表的格式如下：
    ```html
    <ol>
        <li>列表项</li>
    </ol>
    ```
    列表可以控制计数，从1开始，或者从特定数字开始。
    - start属性
      ```html
      <ol start="4">
      ```
    - reversed属性
      ```html
      <ol start="4" reversed>
      ```
    - value属性
      value 属性允许设置列表项指定数值
      ```html
      <li value="2">
      ```
- 定义列表
    定义列表是用来定义术语的。
    定义列表的格式如下：
    ```html
    <dl>
        <dt>术语</dt>
        <dd>术语的定义</dd>
        <dd>单个术语可以有多个描述</dd>
    </dl>
    ```
- 引用
    - 块引用
        一般包围段落，渲染效果是整段缩进。cite属性标明来源，属于SEO。
        引用的格式如下：
        ```html
        <blockquote cite="CITE_SOURCE">
            <p>这是一个引用。</p>
        </blockquote>
        ```
    - 行内引用
        一般包围文字，渲染效果为加上引号。cite属性标明来源，属于SEO。
        引用的格式如下：
        ```html
        <q cite="CITE_SOURCE">这是一个引用。</q>
        ```
    - 引文
        一般包围文字，渲染效果为斜体。最好再加上超链。
        引用的格式如下：
        ```html
        <a href="URL"><cite>这是一个引用。</cite></a>
        ```
- 缩略语
    缩略语是用来定义术语或者简写的，在文中第一次出现简写的时候，请使用`<abbr>`标签，并且用纯文本解释该术语。title属性会导致悬停出详细解释，渲染效果一般是虚下划线。
    缩略语的格式如下：
    ```html
    <abbr title="缩略语">缩略语</abbr>
    ```
- 地址
    这是一种标记联系方式的方式，它可以包含姓名，电话，电子邮件，地址，等等。
    地址的格式如下：
    ```html
    <address>
        <p>
            <a href="HOMEPAGE">NAME</a><br/>
            Shanghai<br/>
            China
        </p>
        <p>
            <a href="mailto:EMAIL">
                EMAIL
            </a>
        </p>
        <p>123456789</p>
    </address>
    ```
- 上下标
    上下标是用来定义上标和下标的，它是一个行内元素，一般包围文字。
    上下标的格式如下：
    ```html
    <sup>上标</sup>
    <sub>下标</sub>
    ```
- 代码
    代码是用来定义代码的，它是一个行内元素，一般包围文字。为了展示代码，HTML中有很多有用的标签，比如`<code>`，`<pre>`，`<var>`，`<kbd>`，`<samp>`等等。
    代码的格式如下：
    ```html
    <code>代码</code> <!-- 用于显示代码(渲染为代码字体) -->
    <pre>代码</pre> <!-- 保留空格和换行，包围<code> -->
    <var>变量</var> <!-- 用于显示变量(斜体) -->
    <kbd>键盘</kbd> <!-- 用于显示键盘输入 -->
    <samp>示例</samp> <!-- 用于显示计算机程序的输出 -->
    ```
- 时间
    时间是用来定义时间的，它是一个行内元素，一般包围文字。
    时间的格式如下：
    ```html
    <!-- 标准简单日期 -->
    <time datetime="2016-01-20">20 January 2016</time>
    <!-- 只包含年份和月份-->
    <time datetime="2016-01">January 2016</time>
    <!-- 只包含月份和日期 -->
    <time datetime="01-20">20 January</time>
    <!-- 只包含时间，小时和分钟数 -->
    <time datetime="19:30">19:30</time>
    <!-- 还可包含秒和毫秒 -->
    <time datetime="19:30:01.856">19:30:01.856</time>
    <!-- 日期和时间 -->
    <time datetime="2016-01-20T19:30">7.30pm, 20 January 2016</time>
    <!-- 含有时区偏移值的日期时间 -->
    <time datetime="2016-01-20T19:30+01:00" >7.30pm, 20 January 2016 is 8.30pm in France</time >
    <!-- 提及特定周 -->
    <time datetime="2016-W04">The fourth week of 2016</time>
    ```
-  超链接
    - href 属性
        超链接一般是一个anchor元素`<a></a>`,href属性指向链接到的目标。这可以是一个绝对或者相对URL
        ```html
        <a href="URL_ADDRESS">百度</a>
        <a href="index.html">本地链接</a>
        ```
        anchor也可以包围一个图片，图片就可以点击跳转
        ```html
        <a href="URL_ADDRESS">
            <img src="IMAGE_ADDRESS" alt="图片">
        </a>
        ```
    - title 属性
        可以给anchor创建title属性，鼠标悬停显示
        ```html
        <a href="URL_ADDRESS" title="TITLE_TEXT">百度</a>
        ```
    - 文档跳转
        HTML_ADDR如果为空，默认为当前文档
        ```html
        <a href="HTML_ADDR#id">跳转到id为id的元素</a>
        ```
    - download属性
        如果链接到一个需要下载的资源，download属性可以提供一个默认的保存文件名。
        ```html
        <a href="URL_ADDRESS" download="FILE_NAME">下载</a>
        ```
    - 电子邮件链接
        mailto协议可以用来创建电子邮件链接，邮件地址会被自动编码。还可以提供很多邮件参数，包括主题，抄送，等等。
        ```html
        <a href="mailto:EMAIL_ADDRESS?subject=SUBJECT_TEXT&cc=CC_ADDRESS">EMAIL_ADDRESS</a>
        ```
- span元素
    这是一个行内元素，一般包围文字。
    span元素的格式如下：
    ```html
    <span>文字</span>
    ```
    span标签没有任何左右，它的存在是为了隔离出一部分行内元素，方便后续设置样式

## 布局
### 有语义的元素
- `<main>` 存放每个页面独有的内容。每个页面上只能用一次 `<main>`，且直接位于 `<body>` 中。最好不要把它嵌套进其他元素。

- `<article>` 包围的内容即一篇文章，与页面其他部分无关（比如一篇博文）。

- `<section>`与 `<article>` 类似，但 `<section>` 更适用于组织页面使其按功能（比如迷你地图、一组文章标题和摘要）分块。一般的最佳用法是：以 标题 作为开头；也可以把一篇 `<article>` 分成若干部分并分别置于不同的 `<section>` 中，也可以把一个区段 `<section>` 分成若干部分并分别置于不同的 `<article>`中，取决于上下文。

- `<aside>` 包含一些间接信息（术语条目、作者简介、相关链接，等等）。

- `<header>` 是简介形式的内容。如果它是 `<body>` 的子元素，那么就是网站的全局页眉。如果它是 `<article>` 或`<section>` 的子元素，那么它是这些部分特有的页眉（此 `<header>` 非彼 标题）。

- `<nav>` 包含页面主导航功能。其中不应包含二级链接等内容。

- `<footer>` 包含了页面的页脚部分。

一个可能的结构如下：
```html
<body><!--页面-->
    <header><!--页眉-->
        <h1>SITE TITLE</h1>
    </header>
    <nav><!--导航-->
        <ul>
            <li>...</li>
        </ul>
    </nav>
    <main><!--主体-->
        <article><!--文章-->
            <h2>ARTICLE TITLE</h2>
            <section>
                ...
            </section>
        </article>
        <aside><!--侧边栏-->
            ...
        </aside>
    </main>
    <footer><!--页脚-->
        ...
    </footer>
</body>
```
### 无语义的元素
如果只是想要把一段内容包装起来，用于相应CSS或者JS，那么可以使用无语义的元素，比如`<div>`和`<span>`，一般来说需要提供`class`属性来便于查询。

无语义元素容易被滥用，应该优先考虑使用有语意元素，这样便于维护。
- `<span>`是内联的无语义元素
```html
<p>
  国王喝得酩酊大醉，在凌晨 1 点时才回到自己的房间，踉跄地走过门口。<span
    class="editor-note"
    >[编辑批注：此刻舞台灯光应变暗]</span
  >.
</p>
```
- `<div>`是块级无语义元素
```html
<div class="shopping-cart">
  <h2>购物车</h2>
  <ul>
    <li>
      <p>
        <a href=""><strong>银耳环</strong></a>：$99.95.
      </p>
      <img src="../products/3333-0985/" alt="Silver earrings" />
    </li>
    <li>...</li>
  </ul>
  <p>售价：$237.89</p>
</div>
```

## HTML Debug 工具

- [W3C Markup Validation Service](https://validator.w3.org/#validate_by_input)


## 媒体

### 图片
基本格式为
```html
<img src="IMG_SRC" alt="ALT_TEXT" width=WIDTH height=HEIGHT title="TITLE">
```
- `src`是图片地址，可以是本地服务器上的路径也可以是一个完整的URL，不建议使用热链接。
- `alt`是图片的替代文字，用于屏幕阅读器，同时在图片无法正常显示的时候可以显示替代文字。
- `width`和`height`是图片的宽度和高度，单位是像素。
- `title`是图片的标题，用于鼠标悬停时显示。

尽管我们可以通过CSS来设置图片的尺寸，位置等，但我们仍然需要考虑图片的动态分辨率问题，在不同视口宽度的浏览器中，我们希望能显示不同分辨率的图片。于是我们可以利用响应式图片技术。

```html
<img
  srcset="elva-fairy-480w.jpg 480w, elva-fairy-800w.jpg 800w"
  sizes="(max-width: 600px) 480px, 800px"
  src="elva-fairy-800w.jpg"
  alt="Elva dressed as a fairy" />
```
- `srcset`
以逗号分隔的一个或多个字符串列表表明一系列用户代理使用的可能的图像。每一个字符串由以下组成：

    - 指向图像的 URL。
    可选地，再加一个空格之后，附加以下的其一：
    - 一个宽度描述符（一个正整数，后面紧跟 w 符号）。该整数宽度除以 sizes 属性给出的资源（source）大小来计算得到有效的像素密度，即换算成和 x 描述符等价的值。
    - 一个像素密度描述符（一个正浮点数，后面紧跟 x 符号）。

    如果没有指定源描述符，那它会被指定为默认的 1x。 在相同的 srcset 属性中混合使用宽度描述符和像素密度描述符时，会导致该值无效。重复的描述符（比如，两个源在相同的 srcset 两个源都是 2x）也是无效的。
    用户代理自行决定选择任何可用的来源。这位它们提供了一个很大的选择余地，可以根据用户偏好或带宽条件等因素来进行选择。
- `sizes`
    表示资源大小的、以逗号隔开的一个或多个字符串。每一个资源大小包括：
    - 一个媒体条件。最后一项一定是被忽略的。
        媒体条件描述视口的属性，而不是图像的属性。例如，如果视口不高于 500px，则建议使用 1000px 宽的资源：(max-height: 500px) 1000px。
    - 一个资源大小的值。
        资源尺寸的值被用来指定图像的预期尺寸。当 srcset 中的资源使用了宽度描述符 w 时，用户代理会使用当前图像大小来选择 srcset 中合适的一个图像 URL。被选中的尺寸影响图像的显示大小（如果没有影响大小的 CSS 样式被应用的话）。如果没有设置 srcset 属性，或者没有属性值，那么 sizes 属性也将不起作用。

如果想为图片提供正文标题，可以使用`<figure>`元素，`<figcaption>`元素包围图片标题。
```html
<figure>
    <img src="IMG_SRC" alt="ALT_TEXT" width=WIDTH height=HEIGHT>
    <figcaption>IMG_TITLE</figcaption>
</figure>
```

如果想要根据视口宽度显示不同的图片，比如宽的显示全景，窄的仅仅显示人像，可以使用`<picture>`元素
```html
<picture>
  <source media="(max-width: 799px)" srcset="elva-480w-close-portrait.jpg" />
  <source media="(min-width: 800px)" srcset="elva-800w.jpg" />
  <img src="elva-800w.jpg" alt="Chris standing up holding his daughter Elva" />
</picture>
```
- `media`属性是媒体条件
- `srcset`是资源列表，source标签可以和上面的srcset-sizes机制无缝衔接，这样一个picture里面有多个图，每个图有多个分辨率
- `img`是兜底图，如果浏览器不支持picture，那么就会显示这个img


### 视频
基本格式如下
```html
<video
  controls
  width="400"
  height="400"
  autoplay
  loop
  muted
  preload="auto"
  poster="poster.png">
  <source src="rabbit320.mp4" type="video/mp4" />
  <source src="rabbit320.webm" type="video/webm" />
  <p>你的浏览器不支持此视频。可点击<a href="rabbit320.mp4">此链接</a>观看</p>
</video>
```
- `controls` 属性用于显示播放控件。
- `width` 和 `height` 属性用于设置视频的宽度和高度，视频不会被拉伸压缩，而是被等比缩放。多余部分用背景填充
- `autoplay` 属性用于自动播放视频。
- `loop` 属性用于循环播放视频。
- `muted` 属性用于静音播放视频。
- `preload` 属性用于预加载视频。此时视频不会自动播放，需要用户点击播放按钮。有三个值可以选择：
    - `none`: 不缓冲文件
    - `metadata`: 只缓冲文件的元数据
    - `auto`: 缓冲文件的元数据和一部分文件
- `poster` 属性用于设置视频的封面图。
- `<source>` 元素用于指定视频的源文件。其中的 `src` 属性用于指定视频文件的路径，`type` 属性用于指定视频文件的类型，供浏览器选择，不提供的话浏览器会挨个试，浪费时间
- `<p>` 元素用于提供视频无法播放时的替代文本。

### 音频
```html
<audio controls>
  <source src="viper.mp3" type="audio/mp3" />
  <source src="viper.ogg" type="audio/ogg" />
  <p>你的浏览器不支持该音频，可点击<a href="viper.mp3">此链接</a>收听。</p>
</audio>
```
除了没有`width`, `height`, `poster`属性，其他都和视频一样。

## 音视频文本

HTML还可以为音视频提供字幕等文本，方式为在`<video>`或者`<audio>`标签内提供`<track>`标签，需要放在`<source>`标签之后。

```html
<video controls>
  <source src="example.mp4" type="video/mp4" />
  <source src="example.webm" type="video/webm" />
  <track kind="subtitles" src="subtitles_es.vtt" srclang="es" label="Spanish" />
</video>
```
- `kind` 属性用于指定字幕的类型，有三个值可以选择：
    - `subtitles`: 翻译字幕
    - `captions`: 字幕
    - `descriptions`: 字幕
- `src` 属性用于指定字幕文件的路径
- `srclang` 属性用于指定字幕文件的语言，用于浏览器识别
- `label` 属性用于指定字幕文件的标题

## 嵌入内容

### 嵌入网页
> Bilibili 外链如果无法播放，报无法连接，将src中URL加上HTTPS协议标头即可
```html
<iframe
    src="https://developer.mozilla.org/zh-CN/docs/Glossary"
    width="100%"
    height="500"
    allowfullscreen
    sandbox>
    <p>
      <a href="/zh-CN/docs/Glossary">
        为不支持 iframe 的浏览器预留的后备链接
      </a>
    </p>
  </iframe>
  ```

- `src` 属性用于指定嵌入网页的地址
- `width` 和 `height` 属性用于设置嵌入网页的宽度和高度
- `allowfullscreen` 属性用于允许嵌入网页全屏显示
- `sandbox` 属性用于设置嵌入网页的安全策略，不提供参数表示开启所有安全限制

### 其它嵌入
| |`<embed>`|`<object>`|
|---|---|---|
|嵌入内容的URL| `src`| `data`|
|嵌入内容的准确媒体类型| `type`| `type`|
|由插件控制的盒子高度和宽度|`height`&`width`| `height`&`width`|
|名称和值|具有这些名称和值的adhoc属性|`param`元素，在`object`元素里面|
|资源不可用时的独立HTML文本|不受支持|包含在`<object>`中，`<param>`元素后面|

## 表格

### 基础
表格由行和列构成，HTML格式为
```html
<table>
    <caption>
        表格标题
    </caption>
  <tr>
    <th>&nbsp;</th>
    <th>Knocky</th>
    <th>Flor</th>
    <th>Ella</th>
    <th>Juan</th>
  </tr>
  <tr>
    <th>Breed</th>
    <td>Jack Russell</td>
    <td>Poodle</td>
    <td>Streetdog</td>
    <td>Cocker Spaniel</td>
  </tr>
  <tr>
    <th>Age</th>
    <td>16</td>
    <td>9</td>
    <td>10</td>
    <td>5</td>
  </tr>
  <tr>
    <th>Owner</th>
    <td>Mother-in-law</td>
    <td>Me</td>
    <td>Me</td>
    <td>Sister-in-law</td>
  </tr>
  <tr>
    <th>Eating Habits</th>
    <td>Eats everyone's leftovers</td>
    <td>Nibbles at food</td>
    <td>Hearty eater</td>
    <td>Will eat till he explodes</td>
  </tr>
</table>
```
- `<tr>`标签表示行，`<th>`标签表示表格标题，`<td>`标签表示单元格。

- `<th>`可以设置`scope`属性，用于设置表格标题的范围，四个值可以选择：
    - `row`: 行
    - `col`: 列
    - `rowgroup`: 行组
    - `colgroup`: 列组
类似的功能还可以用id-header机制完成，为每个th设置id，为每个td设置header：
```html
<thead>
  <tr>
    <th id="purchase">Purchase</th>
    <th id="location">Location</th>
    <th id="date">Date</th>
    <th id="evaluation">Evaluation</th>
    <th id="cost">Cost (€)</th>
  </tr>
</thead>
<tbody>
  <tr>
    <th id="haircut">Haircut</th>
    <td headers="location haircut">Hairdresser</td>
    <td headers="date haircut">12/09</td>
    <td headers="evaluation haircut">Great idea</td>
    <td headers="cost haircut">30</td>
  </tr>

  …
</tbody>
```

- `<td>` 和 `<th>`字段可以设置`rowspan`和`colspan`属性，用于合并单元格。

- `<caption>`标签用于设置表格的标题。放在`<table>`下面


### 表格结构
表格有表头、表体和表尾，分别用`<thead>`、`<tbody>`和`<tfoot>`标签表示。
表头一般是标题，表尾一般出现在表格最后。这些元素有利于无障碍以及样式设置。

### 按列设置样式

按列设置样式可以用`<colgroup>`标签. `<col>`标签用于设置列的样式，`<colgroup>`标签里面可以有多个`<col>`标签，每个标签对应一列。
```html
<table>
  <colgroup>
    <col />
    <col style="background-color: yellow" />
  </colgroup>
  <tr>
    <th>Data 1</th>
    <th>Data 2</th>
  </tr>
  <tr>
    <td>Calcutta</td>
    <td>Orange</td>
  </tr>
  <tr>
    <td>Robots</td>
    <td>Jazz</td>
  </tr>
</table>
```

### 嵌套表格

表格可以嵌套，但是需要注意，嵌套的表格不能有`<caption>`标签，因为`<caption>`标签会被嵌套的表格覆盖。
```html
<table id="table1">
  <tr>
    <th>标题 1</th>
    <th>标题 2</th>
    <th>标题 3</th>
  </tr>
  <tr>
    <td id="nested">
      <table id="table2">
        <tr>
          <td>单元格 1</td>
          <td>单元格 2</td>
          <td>单元格 3</td>
        </tr>
      </table>
    </td>
    <td>单元格 2</td>
    <td>单元格 3</td>
  </tr>
  <tr>
    <td>单元格 4</td>
    <td>单元格 5</td>
    <td>单元格 6</td>
  </tr>
</table>
```


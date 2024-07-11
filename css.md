# CSS 语法基础

## 选择器

### 类型、类和ID选择器
```css
element.<class1>.<class2>#id {
    ...
}
```

### 属性选择器
```css
element[attr] { /* 选择具有 attr 属性的所有元素 */
    ...
}
element[attr="value"] { /* 选择具有 attr 属性且值等于 "value" 的所有元素 */
    ...
}
element[attr="value" i] { /* 选择具有 attr 属性且值等于 "value" （不区分大小写）的所有元素 */
    ...
}
element[attr~="value"] {  /* 选择具有 attr 属性且属性列表中存在值等于 "value" 的所有元素 */
    ...
}
element[attr|="value"] { /* 选择具有 attr 属性且属性值等于 "value" 或以 "value-" 开头的所有元素 */
    ...
}
element[attr^="value"] { /* 选择具有 attr 属性且属性值以 "value" 开头的所有元素 */
    ...
}
element[attr$="value"] { /* 选择具有 attr 属性且属性值以 "value" 结尾的所有元素 */
    ...
}
element[attr*="value"] { /* 选择具有 attr 属性且属性值中任意位置包含 "value" 的所有元素 */
    ...
}
```

### 伪类和伪元素选择器

[伪类和伪元素速查表](https://developer.mozilla.org/zh-CN/docs/Learn/CSS/Building_blocks/Selectors/Pseudo-classes_and_pseudo-elements#%E5%8F%82%E8%80%83%E8%8A%82)
伪类描述的是元素的一种状态
```css
element:hover { /* 选择所有处于 hover 状态的元素 */
    ...
}
element:first-child { /* 选择作为第一个子元素的元素 */
    ...
}
```
**e.g. nth-child伪类的用法**
```css
element:nth-child(2n) { /* 选择位于偶数位置的element元素 */
    ...
}
element.class:nth-child(2n+1) { /* 选择位于奇数位置的且拥有class的element元素 */
    ...
}
element:nth-child(2n+1 of .class) { /* 选择拥有class的element元素中奇数位置的那些 */
    ...
}
```
伪元素描述的是元素的部分
```css
element::first-line { /* 选择所有元素的首行 */
    ...
}
element::first-letter { /* 选择所有元素的首字母 */
    ...
}
element::before { /* 元素中所有内容之前 */
    content: "..."; /* 这里可以设置插入内容 */
}
element::after { /* 元素中所有内容之后 */
    content: "..."; /* 这里可以设置插入内容 */
}
```

### 关系选择器

```css
element1 element2 { /* 选择所有 element2 元素，且 element2 是 element1 的后代 */
    ...
}

element1 > element2 { /* 选择所有 element2 元素，且 element2 是 element1 的直接子元素 */
    ...
}

element1 + element2 { /* 选择所有 element2 元素，且 element2 是 element1 的下一个兄弟元素 */
    ...
}

element1 ~ element2 { /* 选择所有 element2 元素，且 element2 是 element1 的后续兄弟元素 */
    ...
}
```

## 层叠层

层叠层是CSS中用于区分样式来源的概念。有多种创建姿势
```css
@layer theme，layout，utilities; /* 创建三个层叠层, 但并没有添加样式 */

@layer layout { /* 创建一个名为layout的层叠层 */
  main {
    display: grid;
  }
}

@layer { /* 创建一个匿名层叠层 */
  body {
    margin: 0;
  }
}

@media (min-width: 600px) { /* 创建一个基于媒体查询的条件层叠层*/
  @layer layout {
    main {
      grid-template-columns: repeat(3, 1fr);
    }
  }
}

/* 将外部样式表导入名为components的层叠层 */
@import url("components-lib.css") layer(components); 
/* 将外部样式表导入components中名为dialog的嵌套层 */
@import url("dialog.css") layer(components.dialog); 
/* 将外部样式表导入一个匿名的层叠层 */
@import url("marketing.css") layer();
/* 将外部样式表导入一个条件层叠层 */
@import url("ruby-narrow.css") layer(international) supports(display: ruby) and (width < 32rem);

/* 嵌套层叠层 */
@layer layout {
  @layer header {
    nav {
      display: flex;
    }
  }
}
```
如果在层叠层创建语句之前，该层叠层已经存在，那么本语句定义的样式会被添加到该层中去。

## 样式的优先级

1. **相关声明**：找到所有具有匹配每个元素的选择器的声明代码块。
2. **重要性**：根据规则是普通还是重要对规则进行排序。重要的样式是指设置了 !important 标志的样式。
3. **来源**：在两个按重要性划分的分组内，按作者、用户或用户代理这几个来源对规则进行排序。
    至此，我们将样式重要性从小到大分为八个分组：
    - 用户代理普通样式
    - 用户普通样式
    - 作者普通样式
    - 正在动画的样式
    - 作者重要样式
    - 用户重要样式
    - 用户代理重要样式
    - 正在过渡的样式
4. **层**：在六个按重要性和来源划分的分组内，按层叠层进行排序。普通声明的层顺序是从创建的第一个到最后一个，然后是未分层的普通样式。对于重要的样式，这个顺序是反转的，但保持未分层的重要样式优先权最低。
    考虑内联样式，对于同一来源的样式，目前的排序是：
    - earlier Layer 普通样式
    - later Layer 普通样式
    - 未分层普通样式
    - 内联普通样式
    - 动画样式
    - 未分层重要样式
    - later Layer 重要样式
    - earlier Layer 重要样式
    - 内联重要样式
    - 过渡样式
5. **优先级**：对于来源层中优先权相同的竞争样式，按优先级对声明进行排序。
    样式优先级是由选择器的类型决定的。从上到下根据数量记分，打平进入下一个级别。
    - 内联样式：
    - ID 选择器：
    - 类、伪类和属性选择器：
    - 元素和伪元素选择器：

    > 否定（:not()）和任意匹配（:is()）伪类本身对优先级没有影响，但它们的参数则会带来影响。参数中，对优先级算法有贡献的参数的优先级的最大值将作为该伪类选择器的优先级。
    > 通用选择器（*）、组合符（+、>、~、' '）和调整优先级的选择器（:where()）不会影响优先级。
6. **出现顺序**：当两个来源层的优先权相同的选择器具有相同的优先级时，最后声明的具有最高优先级的选择器的属性值获胜。

## 盒子模型

### 盒子的展示方式（display）

- **block**：块级元素，默认宽度为父元素的100%，高度由内容决定，可以设置宽高，margin和padding。
- **inline**：行内元素，默认宽度由内容决定，高度由内容决定，宽高无效，margin和padding有效。
- **inline-block**：行内块级元素，默认宽度由内容决定，高度由内容决定，可以设置宽高，margin和padding。

### 盒子的属性

- **width**：宽度
- **height**: 高度
- **padding**：内部内容到边框的距离
- **margin**：边框到外部盒子的距离
- **border**：边框属性

### 盒子标准
- CSS标准盒子模型：
盒子边框总宽度 = width + 2 * padding + 2 * border-width.
高度同理

- CSS替代盒子模型：(设置box-sizing: border-box)
盒子边框总宽度 = width.
高度同理

## 背景

### 背景颜色 background-color
可以设置为颜色名，十六进制，rgb，rgba，hsl，hsla。参见[颜色](https://developer.mozilla.org/zh-CN/docs/Web/CSS/color_value)

### 背景图片 background-image

- 图片路径：url(path)
大图不缩小，小图默认重复平铺
```css
background-image: url(path);
```
- 图片重复方式 background-repeat：
    - repeat：默认，重复图片直到填满盒子
    - no-repeat：不重复图片
    - repeat-x：水平重复图片
    - repeat-y：垂直重复图片
    - space：重复图片，但图片之间留有空间
    - round：重复图片，但图片之间留有空间，直到填满盒子
- 图片大小 background-size：
    - auto：默认，图片原始大小
    - contain：图片大小适应盒子大小，保持长宽比不变，可能有空白
    - cover：图像完全覆盖盒子，保持长宽比不变，可能显示不完全
    - 直接设置长度(px, em, rem, 百分比)
- 图片位置 background-position：
    左上角（0，0），x水平，y竖直
    可以使用关键字（top bottom center），长度，百分比
- 图片附着方式 background-attachment：
    - scroll：默认，背景图片随滚动而滚动
    - fixed：背景图片固定，不随滚动而滚动
    - local: 背景图片随元素内容滚动，但背景位置固定
- 渐变：
参见[渐变](https://developer.mozilla.org/zh-CN/docs/Web/CSS/gradient)
    ```css
    linear-gradient(ang, color1, transp1, color2, transp2)
    radial-gradient(shape, color1, transp1, color2, transp2)
    ```
- 多个图片
```css
background-image: url(image1.png), url(image2.png), url(image3.png), url(image4.png);
background-repeat: no-repeat, repeat-x, repeat;
background-position: 10px 20px, top right;
```
不同属性的每个值，将与其他属性中相同位置的值匹配。例如，上面的 image1 的 background-repeat 值将是 no-repeat。但是，当不同的属性具有不同数量的值时，会发生什么情况呢？答案是较小数量的值会循环

### background 简写

background 属性被指定多个背景层时，使用逗号分隔每个背景层。
每一层的语法如下：

- 在每一层中，下列的值可以出现 0 次或 1 次：
    - attachment
    - bg-image
    - position
    - bg-size
    - repeat-style
- bg-size 只能紧接着 position 出现，以"/"分割，如： "center/80%".
- background-color 只能被包含在最后一层。

```css
.box {
  background:
  scroll linear-gradient(105deg, rgb(255 255 255 / 20%) 39%, rgb(51 56 57 / 100%) 96%) center center / 400px 200px no-repeat, 
  url(big-star.png) center no-repeat, 
  rebeccapurple;
}
```

## 边框
### 边框属性
```css
.box1 {
  border-width: 1px;
  border-style: solid/dashed/dotted/double/groove/ridge/inset/outset/hidden;
  border-color: black;
}

.box2 { /* 简写 */
  border: 1px solid black;
}

.box3 { /* 单独设置 */
  border-top: 1px solid black;
  border-right: 1px solid black;
  border-bottom: 1px solid black;
  border-left: 1px solid black;
}

.box4 { /* 单独细力度设置 */
    border-top-width: 1px;
    border-top-style: solid;
    border-top-color: black;
}
```
### 圆角
盒子上的圆角是通过使用 border-radius 属性和与盒子的每个角相关的普通属性来实现的。两个长度或百分比可以作为一个值，第一个值定义水平半径，第二个值定义垂直半径。在很多情况下，你只会传入一个值，这个值会被用于这两个。

```css
.box5 { /* 圆角 */
  border-radius: 10px;
  border-top-right-radius: 1em 10% /* 水平半径 垂直半径，百分比是终点在对应边上的位置 */
}
```
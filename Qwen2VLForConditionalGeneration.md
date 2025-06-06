# Qwen2里面的RoPE究竟是怎么搞的

## 输入预处理
在调用模型之前，Processor会先把文本和图像处理好，我们先来看看图像预处理过程：

### 图像预处理
假设每张图像(numpy格式)大小为`1420 * 720 *3` (HWC)。每张图经过Image Processor的如下操作:

1. [smart_resize](https://github.com/huggingface/transformers/blob/main/src/transformers/models/qwen2_vl/image_processing_qwen2_vl.py#L155)，图像的长宽都会变成`factor=grid_size * merge_size = 14 * 2`的倍数, 即`1428*728*3`.
2. 把图像的通道维度换到第二维, 并且添加时间维度, 即`(1, 3, 1428, 728)`. 
3. 在时间维度上复制一份, 变成`(2, 3, 1428, 728)`，记为`(t, c, H, W)`
4. 网格化, 时间维度一格是两张图, H维度一格是两个patch, 一个patch14个像素, W和H一样. 现在shape变为(1, 2, 3, grid_h // 2, 2, 14, grid_w // 2, 2, 14), 记为`(t, t_patch_size, c, h // merge_size, merge_size, patch_size, w // merge_size, merge_size, patch_size)`
5. 调整view, 变成`(t, h // merge_size, w // merge_size, merge_size, merge_size, c, t_patch_size, patch_size, patch_size)`
6. thw和后面的`merge_size * merge_size`乘起来, 后三组也乘起来, 变成`(t*h*w, 3*2*14*14=1176)`

同时我们拿到每个图片的grid尺寸`（t, h, w）`。

Image Processor最后返回两个东西:

1. pixel_values: (n, 1176), 是每个图片单独的patches在第一个维度上extend起来的东西
2. image_grid_thw: (N, 3), N是图片张数, 这个东西包含每个图片的thw值.

### 文本预处理
假设我们的文本是`a b c d <|vision_start|><|image_pad|><|vision_end|> e f g <|vision_start|><|image_pad|><|vision_end|>`，在
处理的时候，`<|image_pad|>`会被扩展成`t_grid * w_grid // MERGE_SIZE * h_grid // MERGE_SIZE`个`<|image_pad|>`，最后tokenize成为input_ids。

最终我们拿到
- `input_ids`: `[B, seqlen]`
- `pixel_value`: `[n*t_grid*w_grid*h_gird, channel*temporal*w*h]`
- `grid_thw`: `[n, 3]`
其中n为图片个数，注意根据`grid_thw`我们可以知道`pixel_value`中每个patch对应哪一张图片的哪一个位置，这对我们后面计算二维ROPE很有用

## prepare_inputs_for_genration
> 不知道这个函数有啥作用的话建议先去看GenerateMixin里面的[generate方法](https://github.com/huggingface/transformers/blob/main/src/transformers/generation/utils.py#L1906)。在generate方法里面会检查各种生成参数，设置KV Cache，设置Attention Mask，并根据你的`Generate Mode`去使用对应的生成策略。我们使用的是Sample策略，也是最简单的一种。于是被分发到`_sample`方法中，在那里面我们会在调用模型forward方法之前先调用模型的`prepare_inputs_for_generation`方法来处理输入。 

首先，获取缓存部分的`input_ids`，如果没有位置编码的话，要利用[self.get_rope_index](https://github.com/huggingface/transformers/blob/main/src/transformers/models/qwen2_vl/modeling_qwen2_vl.py#L1451)根据文本部分的`input_ids`和图片部分的`image_grid_thw`来计算位置编码的index。计算方案如下
```
Calculate the 3D rope index based on image and video's temporal, height and width in LLM.

        Explanation:
            Each embedding sequence contains vision embedding and text embedding or just contains text embedding.

            For pure text embedding sequence, the rotary position embedding has no difference with mordern LLMs.
            Examples:
                input_ids: [T T T T T], here T is for text.
                temporal position_ids: [0, 1, 2, 3, 4]
                height position_ids: [0, 1, 2, 3, 4]
                width position_ids: [0, 1, 2, 3, 4]

            For vision and text embedding sequence, we calculate 3D rotary position embedding for vision part
            and 1D rotary position embeddin for text part.
            Examples:
                Assume we have a video input with 3 temporal patches, 2 height patches and 2 width patches.
                input_ids: [V V V V V V V V V V V V T T T T T], here V is for vision.
                vision temporal position_ids: [0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2]
                vision height position_ids: [0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1]
                vision width position_ids: [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
                text temporal position_ids: [3, 4, 5, 6, 7]
                text height position_ids: [3, 4, 5, 6, 7]
                text width position_ids: [3, 4, 5, 6, 7]
                Here we calculate the text start position_ids as the max vision position_ids plus 1.
```
最后vision部分的index会和text部分的index在序列维度上拼接起来，形成一个形状为`[3, B, seqlen]`的`position_ids`，以及一个形状为`[B, 1]`的`mrope_position_delta`。
后者是序列中最大index和实际seqlen的差别（有图片的话就会有差别），肯定小于等于0。

注意如果使用`StaticCache`，那么`attention_mask`要做适配

最后把计算出来的`position_ids`，`rope_deltas`，`attention_mask`更新到`model_inputs`中并返回。

## Qwen2VLForConditionalGeneration的forward方法

终于来到这里了，首先`input_ids`会被embed，变成`inputs_embeds`，形状为`[B, seqlen, config.hidden_size=1536]`，然后`pixel_values`会被模型中的视觉头`self.vision`[进行编码](https://github.com/huggingface/transformers/blob/main/src/transformers/models/qwen2_vl/modeling_qwen2_vl.py#L955)，形成`image_embeds`。这个`self.vision`是一个ViT网络

### 图像patches的编码--ViT

这一部分在[Qwen2VisionTransformerPretrainedModel](https://github.com/huggingface/transformers/blob/main/src/transformers/models/qwen2_vl/modeling_qwen2_vl.py#L955)里面

对于输入的`[num_patches, 3*2*14*14=1176]`的图片，我们首先进行一次Conv3d的投影，得到`[num_patches, embed_dim]`的`hidden_states`，这里`embed_dim=1280`

随后我们计算图像上的相向量，
- 第一步是获得每个patch的行号和列号`pos_ids`，这可以根据`grid_thw`很方便地计算出来，这个`pos_ids`的形状为`[num_patches, 2]`
- 第二步是计算rotary embedding中的`mθ`，对于每一个位置，有一个长度为`head_dim // 4`的`inv_freq`向量: `1 / base**(torch.arange(0, head_dim // 2, 2, dtype=torch.float) / （head_dim // 2）)`。这里因为`num_head=16`，所以`head_dim = 1280 / 16 = 80`，`inv_freq`长度为20。
对于一维序列中的位置m，该位置的相向量为`m * inv_freq`。所以，输入一个长度`seqlen`，我们可以先预备好一个形状为`[seqlen, head_dim//4]`的相谱：
    ```python
    seq = torch.arange(seqlen)
    freqs = torch.outer(seq, self.inv_freq)
    ```
- 第三步是根据每个patch的行号列号去索引相谱，得到该patch两个方向的相向量`rotary_pos_emb`
    ```python
    rotary_pos_emb = rotary_pos_emb_full[pos_ids].flatten(1)
    ```
    索引出来本来形状是`[num_patches, 2, head_dim // 4]`，但是把第一个维度之后全部flatten了，所以最后的形状是`[num_patches, head_dim // 2 = 40]`，用**θ**来表示20个θ的话，那么现在`rotary_pos_emb`每个位置上是[x **θ**，y **θ**]

    > **补充说明**：为什么freqs的长度是`head_dim // 4`?
    > 参考[苏神的文章](https://spaces.ac.cn/archives/8397#mjx-eqn-eq%3Are)，对于二维位置编码，旋转矩阵是4*4的对角分块矩阵，左上角对应`xθ`，右下角对应`yθ`。那么对于一个维度为`head_dim`的feature，需要的`θ`个数就是
    > `head_dim // 4`

接下来计算`cu_seqlens`，即每个图片的patch范围，在我们的例子里`cu_seqlens = [0, 5304, 10608]`

接下来过16层AttentionBlock，在每个AttentionBlock里面进行一次attention，一次FFN。这一部分在[Qwen2VLVisionBlock](https://github.com/huggingface/transformers/blob/main/src/transformers/models/qwen2_vl/modeling_qwen2_vl.py#L433)里面。
```python
    def forward(self, hidden_states, cu_seqlens, rotary_pos_emb) -> torch.Tensor:
        hidden_states = hidden_states + self.attn(self.norm1(hidden_states), cu_seqlens=cu_seqlens, rotary_pos_emb=rotary_pos_emb)
        hidden_states = hidden_states + self.mlp(self.norm2(hidden_states))
        return hidden_states
```
每次Attention是由[VisionSdpaAttention](https://github.com/huggingface/transformers/blob/main/src/transformers/models/qwen2_vl/modeling_qwen2_vl.py#L426)完成的，它的计算如下。可以看到，每一层都算了一次位置编码并且apply：
- 首先计算多头QKV，每个的形状都是`[seqlen, num_heads=16, head_dim=80]`
- 对QK增添位置编码，以Q为例。
    - 把Q扩充一个维度，变成`[1, seqlen, num_heads, head_dim]`
    - 利用`rotary_pos_emb`计算cos和sin向量
        ```python
        cos = freqs.cos() # [seqlen, head_dim // 2], [(cos(xθ), cos(yθ)), ...]
        sin = freqs.sin()
        cos = cos.unsqueeze(1).repeat(1, 1, 2).unsqueeze(0).float() # [1, seqlen, 1, head_dim]
        sin = sin.unsqueeze(1).repeat(1, 1, 2).unsqueeze(0).float()
        ```
    - 利用公式`x_rotary = x * cos + rotate(x) * sin`进行编码，这里每个头都被广播了，位置编码是一样的
        ```python
        output = (tensor * cos) + (rotate_half(tensor) * sin)
        output = output.to(orig_dtype)
        ```
    - 再把第一个维度squeeze掉，最后得到的q和k形状都是`[seqlen, num_heads=16, head_dim=80]`
- 计算`attention_mask`，用于控制**每张图片只和自己做attention**，这里用到了`cu_seqlens`
    ```python
        attention_mask = torch.zeros([1, seq_length, seq_length], device=q.device, dtype=torch.bool)
        for i in range(1, len(cu_seqlens)):
            attention_mask[..., cu_seqlens[i - 1] : cu_seqlens[i], cu_seqlens[i - 1] : cu_seqlens[i]] = True
    ```
- 最后进行经典的sdpa attention，注意要把`num_heads`维度交换到前面去，最后再换回来
    ```python
        q = q.transpose(0, 1)
        k = k.transpose(0, 1)
        v = v.transpose(0, 1)
        attn_output = F.scaled_dot_product_attention(q, k, v, attention_mask, dropout_p=0.0)
        attn_output = attn_output.transpose(0, 1)
        attn_output = attn_output.reshape(seq_length, -1)
        attn_output = self.proj(attn_output)
        return attn_output
    ```

最后进行patch的融合，2*2的相邻patch融合成一个。操作如下，`self.ln_q`是layernorm，`self.mlp`是一个两层全连接，中间用GELU激活。维度变化是`[config.embed_dim=1280 * 4 -> config.embed_dim=1280 * 4 -> config.hidden_size=1536]`
```python 
    x = self.mlp(self.ln_q(x).view(-1, self.hidden_size))
    return x
```

ViT 最后输出的`image_embeds`的shape为`[2652, 1536]`，其中`2652 = 10608 // 4`

### 图像embedding和文本embedding的融合

现在我们的`inputs_embeds`和`image_embeds`的`hidden_size`都统一为了`config.hidden_size=1536`，并且`inputs_embeds`中的image token恰好就有`image_embeds`第一维度那么多个。那么可以直接把`image_embeds`嵌入到对应位置，这在代码里是通过一个`masked_scatter`来实现的
```python
image_mask = (
        (input_ids == self.config.image_token_id)
        .unsqueeze(-1)
        .expand_as(inputs_embeds)
        .to(inputs_embeds.device)
    )
print("image_mask.shape: ", image_mask.shape)
image_embeds = image_embeds.to(inputs_embeds.device, inputs_embeds.dtype)
inputs_embeds = inputs_embeds.masked_scatter(image_mask, image_embeds)
```

把`attention_mask`传到相同device之后，就可以把图像和文本融合好的`embedding`送给传统的Transformer去做attention了。还记得之前算的`position_ids`，`attention_mask`吗，这里一并传入Transformer。

### 对全部embedding做计算--Qwen2VLModel

现在我们把融合之后的`inputs_embeds`送给Qwen2VLModel进行计算，在forward里面会先根据`position_ids`计算好`rotary_emb`，然后一层层送入decode layer进行一次SdpaAttention，具体的类是[Qwen2VLSdpaAttention](https://github.com/huggingface/transformers/blob/main/src/transformers/models/qwen2_vl/modeling_qwen2_vl.py#L729)。

> 我们之前计算的`position_ids`形状为`[3, 1, seqlen]`，首先我们会在`Qwen2VLRotaryEmbedding`类里面计算`positional_embedding`，具体就是首先得到一个`self.inv_freq`，形状为`[3, 1, dim=64]`，然后和`position_ids`做outter product，最后一维复制一遍，再取cos和sin，一并返回，维度均为`[3, 1, seqlen, 128]`

> 在SpdaAttention里面，首先计算QKV，这里KV的头数其实是`num_heads`的一个因数，Q不变，是为GQA。然后通过`apply_multimodal_rotary_pos_emb`[函数](https://github.com/huggingface/transformers/blob/main/src/transformers/models/qwen2_vl/modeling_qwen2_vl.py#L171)根据`position_embeddings`对QK进行位置编码。注意这里的细节：我们之前计算的`position_ids`是按照thw的顺序在第一个维度cat起来的。所以现在的`position_embeddings`也是这个顺序。

> Qwen认为，64维的`inv_freq`里面，一部分角度编码t，一部分角度编码h，一部分角度编码w。这个分割做在`config.mrope_section`里面。去看一下就知道，他设定的值为`[16, 24, 24]`。由于我们把虚部都统一放在维度的后一半儿，并且把cos，sin复制了一遍，所以也要先把`mrope_section`复制一遍，变成`[16, 24, 24, 16, 24, 24]`。接着分割cos和sin的最后一维，并按照`[t, h, w, t, h, w]`的顺序在第一维上选，重新在最后一维上拼接，并扩展head group的维度。最终形成`[B, 1, seqlen, 128]`的cos和sin。（不是，这也不是三位Rotary啊？正儿八经的三位Rotary应该是`[tθ, hθ, wθ]`的cos和sin来搞吧，它这是`[tθ[:16], hθ[17:40], wθ[41: 64]]`的cos和sin搞的）

```python
cos = torch.cat([m[i % 3] for i, m in enumerate(cos.split(mrope_section, dim=-1))], dim=-1).unsqueeze(
    unsqueeze_dim
)
sin = torch.cat([m[i % 3] for i, m in enumerate(sin.split(mrope_section, dim=-1))], dim=-1).unsqueeze(
    unsqueeze_dim
)
```
> Anyway，我们根据cos和sin就可以愉快地套公式编码了，编完之后返回QK。接着我们会把KV拿去**更新KV Cache**，KV Cache的update方法会返回拼上了缓存值的全量KV。随后把KV的Head Group展开（interleave_repeat）就可以拿去和Q做SpdaAttention啦~

每一层都会对QK进行位置编码，随后对KV Cache进行update，接着进行GQA，把头拼好，返回output和新的KV Cache。










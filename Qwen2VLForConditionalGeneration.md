# Qwen2里面的RoPE究竟是怎么搞的

## 输入预处理
在调用模型之前，Processor会先把文本和图像处理好，我们先来看看图像预处理过程：

### 图像预处理
假设每张图像大小为`720*1140*3`。每张图经过Image Processor的
[smart_resize](https://github.com/huggingface/transformers/blob/main/src/transformers/models/qwen2_vl/image_processing_qwen2_vl.py#L155)，图像的长宽都会变成`patch_size=14`的倍数并添加batch维度，即`1*3*1428*728`，然后图像会**在时间维度上被复制一份**，并变成patches，维度为`5304*1176=(1 * (1428/14)*(728/14))*(3*2*14*14)`，
前面的维度是grid大小`（t_grid, w_grid, h_grid）`，后面的维度就是一个patch的大小`（channel，temporal，w，h）`。

假设我们有2张图片，那么每个图片都会被[复制一份](https://github.com/huggingface/transformers/blob/main/src/transformers/models/qwen2_vl/image_processing_qwen2_vl.py#L374)（这里很神奇啊，可能是bug）。
最后每个patch会在第一个维度上拼起来，最终形成一个`10608*1176`的`pixel_values`。（相当于4张图的patch量）

同时我们能够拿到`image_grid_thw`，即每个图片的grid尺寸`（t_grid, w_grid, h_grid）`。

### 文本预处理
假设我们的文本是`a b c d <|vision_start|><|image_pad|><|vision_end|> e f g <|vision_start|><|image_pad|><|vision_end|>`，在
处理的时候，`<|image_pad|>`会被替换成`w_grid // MERGE_SIZE, h_grid // MERGE_SIZE`个`<|placeholder|>`，最后tokenize成为input_ids。

最终我们拿到
- `[B, seqlen]`的`input_ids`
- `[n*t_grid*w_grid*h_gird, channel*temporal*w*h]`的`pixel_value`
- `[n, 3]`的`grid_thw`
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

每一层都会对QK进行位置编码，随后对KV Cache进行update，接着进行GQA，把头拼好，返回output和新的KV Cache。










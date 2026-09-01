# yiming

这是一个从零训练小型语言模型的实验仓库。

当前主线位于 [`minillm/`](minillm/)，目标是参考 [MiniMind](https://github.com/jingyaogong/minimind) 的思路，用 PyTorch 原生实现一条可以理解、可以运行、可以逐步扩展的训练链路：

```text
tokenizer → pretrain → SFT → evaluation / generation → optional DPO or RL
```

仓库原有的 `index.html` 是一个与本项目无关的旧网页，暂时保留但不参与模型训练。

快速开始请看 [`minillm/README.md`](minillm/README.md)。

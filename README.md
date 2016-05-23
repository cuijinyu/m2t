
## M2T

通过磁力链接获取.torrent文件。

## 动机

一些不可描述的资源，在部分下载工具上使用磁力链接无法下载，但使用其种子文件却可以正常下载。

因此希望找寻一种方法能够在不借助种子库的情况下将磁力链接转换为种子文件。

## 原理

1. 通过[DHT协议](http://www.bittorrent.org/beps/bep_0005.html)找到拥有.torrent文件的peer；
2. 通过[BEP09](http://www.bittorrent.org/beps/bep_0009.html)从这些peer获取.torrent文件。

## 进度

* 已能够通过DHT网络获取到拥有资源的peer

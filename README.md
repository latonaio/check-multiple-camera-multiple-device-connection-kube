# check-multiple-camera-multiple-device-connection-kube
check-multiple-camera-multiple-device-connection-kube は、主にエッジコンピューティング環境において、USBで接続された複数のカメラ情報を検出するマイクロサービスです。  
check-multiple-camera-multiple-device-connection-kube は、USBで接続されている複数のカメラの接続情報を取得し、他マイクロサービスへ配信します。  
配信はRabbitMQを通じて行われます。  

配信されるデータは下記の二種類です。

- 接続されているデバイスのリスト
- 各デバイスのシリアル番号のリスト

デバイスのリストは`v4l2-ctl`コマンドを使用して取得されます。

# 動作環境
check-multiple-camera-connection-kubeはAIONのプラットフォーム上での動作を前提としています。  
使用する際は、事前にAIONの動作環境を用意してください。   
- OS: Linux OS     
- CPU: ARM/AMD/Intel   
- Kubernetes     
- AION   

# セットアップ
このリポジトリをクローンし、makeコマンドを用いてDocker container imageのビルドを行ってください。   
```
$ cd check-multiple-camera-connection-kube
$ make docker-build
```

## デプロイ on AION
AION上でデプロイする場合、services.yamlに次の設定を追加してください。
```
check-multiple-camera-multiple-device-connection:
    scale: 1
    startup: yes
    always: yes
    privileged: yes
    env:
      MYSQL_HOST: mysql
      MYSQL_USER: XXXXXX
      MYSQL_PASSWORD: XXXXXXXXXX
      MYSQL_DATABASE: XXXXXXXXXX
      DEST_DEVICE_NAME: XXXXXXX
      RABBITMQ_URL: amqp://guest:guest@rabbitmq:5672/pokayoke
      QUEUE_TO_CAMERA: stream-usb-video-by-rtsp-multiple-camera-queue
      QUEUE_TO_CAMERA_2: stream-usb-video-by-rtsp-multiple-camera-2-queue
      QUEUE_TO_OUTPUT: import-multiple-camera-connection-queue
    volumeMountPathList:
      - /dev:/dev
```

# I/O
### input
なし

### output
- device_list: 取得したデバイスリスト   
- devices: 各デバイスのシリアル番号のリスト
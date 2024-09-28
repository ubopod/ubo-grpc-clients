import { inflate } from "fflate";
import {
  DispatchActionRequest,
  SubscribeEventRequest,
  SubscribeEventResponse,
} from "./generated/store/v1/store_pb";
import { StoreServiceClient } from "./generated/store/v1/StoreServiceClientPb";
import {
  Action,
  AudioPlayAudioEvent,
  DisplayCompressedRenderEvent,
  Event,
  Key,
  KeypadKeyPressAction,
  Notification,
  NotificationsAddAction,
} from "./generated/ubo/v1/ubo_pb";

const store = new StoreServiceClient("http://localhost:8080", null, null);

function dispatchSampleNotification() {
  const notification = new Notification();
  notification.setTitle("Hello");
  notification.setContent("World");

  const notificationsAddAction = new NotificationsAddAction();
  notificationsAddAction.setNotification(notification);

  const action = new Action();
  action.setNotificationsAddAction(notificationsAddAction);

  const dispatchActionRequest = new DispatchActionRequest();
  dispatchActionRequest.setAction(action);

  store.dispatchAction(dispatchActionRequest);
}

function subscribeToRenderEvents() {
  const event = new Event();
  event.setDisplayCompressedRenderEvent(new DisplayCompressedRenderEvent());

  const subscribeEventRequest = new SubscribeEventRequest();
  subscribeEventRequest.setEvent(event);

  const stream = store.subscribeEvent(subscribeEventRequest);

  stream.on("end", () => setTimeout(subscribeToRenderEvents, 1000));
  stream.on("data", (response: SubscribeEventResponse) => {
    const compressedData = response
      .getEvent()
      ?.getDisplayCompressedRenderEvent()
      ?.getCompressedData_asU8();
    const rectangle = response
      .getEvent()
      ?.getDisplayCompressedRenderEvent()
      ?.getRectangleList();
    if (!compressedData || !rectangle) {
      return;
    }
    inflate(compressedData, (error, data) => {
      if (error) {
        console.error(error);
        return;
      }
      if (data) {
        const [, , width, height] = rectangle;
        const canvas = document.getElementById("canvas") as HTMLCanvasElement;
        canvas.width = width;
        canvas.height = width;

        const context = canvas.getContext("2d");

        if (!context) return;

        context.putImageData(
          new ImageData(new Uint8ClampedArray(data), width, height),
          0,
          0,
        );
      }
    });
  });
}

function createWavFile(
  samples: Uint8Array,
  sampleRate: number,
  numChannels: number,
  bitsPerSample: number,
): Blob {
  const header = new ArrayBuffer(44);
  const view = new DataView(header);

  /* Write WAV file header */
  const blockAlign = (numChannels * bitsPerSample) / 8;
  const byteRate = sampleRate * blockAlign;
  const dataSize = samples.length;

  // 'RIFF' chunk descriptor
  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + dataSize, true); // File size minus first 8 bytes
  writeString(view, 8, "WAVE");

  // 'fmt ' sub-chunk
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true); // SubChunk1Size for PCM
  view.setUint16(20, 1, true); // AudioFormat (1 = PCM)
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);

  // 'data' sub-chunk
  writeString(view, 36, "data");
  view.setUint32(40, dataSize, true);

  function writeString(view: DataView, offset: number, string: string) {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  }

  const wavBuffer = new Uint8Array(header.byteLength + samples.length);
  wavBuffer.set(new Uint8Array(header), 0);
  wavBuffer.set(samples, header.byteLength);

  return new Blob([wavBuffer], { type: "audio/wav" });
}

function subscribeToAudioEvents() {
  const event = new Event();
  event.setAudioPlayAudioEvent(new AudioPlayAudioEvent());

  const subscribeEventRequest = new SubscribeEventRequest();
  subscribeEventRequest.setEvent(event);

  const stream = store.subscribeEvent(subscribeEventRequest);

  stream.on("end", () => setTimeout(subscribeToAudioEvents, 1000));
  stream.on("data", (response: SubscribeEventResponse) => {
    const audioEvent = response.getEvent()?.getAudioPlayAudioEvent();

    if (!audioEvent) {
      return;
    }

    const sample = audioEvent.getSample_asU8();
    const rate = audioEvent.getRate();
    const width = audioEvent.getWidth();
    const channels = audioEvent.getChannels();
    const audio = new Audio();
    const audioBlob = createWavFile(sample, rate, channels, width * 8);
    const url = URL.createObjectURL(audioBlob);
    audio.src = url;

    audio.play();
  });
}

dispatchSampleNotification();
subscribeToRenderEvents();
subscribeToAudioEvents();

const KEYS = {
  "1": Key.KEY_L1,
  "2": Key.KEY_L2,
  "3": Key.KEY_L3,
  Backspace: Key.KEY_HOME,
  ArrowLeft: Key.KEY_BACK,
  h: Key.KEY_BACK,
  ArrowUp: Key.KEY_UP,
  k: Key.KEY_UP,
  ArrowDown: Key.KEY_DOWN,
  j: Key.KEY_DOWN,
};
type KeyType = keyof typeof KEYS;

function isValidKey(key: string): key is KeyType {
  return key in KEYS;
}

document.addEventListener("keyup", ({ key }) => {
  if (isValidKey(key)) {
    const keypadKeyPressAction = new KeypadKeyPressAction();
    keypadKeyPressAction.setKey(KEYS[key]);

    const action = new Action();
    action.setKeypadKeyPressAction(keypadKeyPressAction);

    const dispatchActionRequest = new DispatchActionRequest();
    dispatchActionRequest.setAction(action);

    store.dispatchAction(dispatchActionRequest);
  }
});

import * as grpc from "@grpc/grpc-js";
import * as protoLoader from "@grpc/proto-loader";
import uboApp from "./generated-protobufjs";

const uboAppGrpc = grpc.loadPackageDefinition(
  protoLoader.loadSync("store/v1/store.proto", {
    includeDirs: ["../../proto/"],
    keepCase: false,
    defaults: true,
    oneofs: true,
  }),
);

const store = uboApp.store.v1;
const ubo = uboApp.ubo.v1;

// Create a client instance
const client: InstanceType<typeof store.StoreService> = new (
  uboAppGrpc as any
).store.v1.StoreService(
  `${process.env.GRPC_HOST || "localhost"}:${process.env.GRPC_PORT || "50051"}`,
  grpc.credentials.createInsecure(),
);

// Prepare the request
const request = new store.DispatchActionRequest({
  action: {
    notificationsAddAction: {
      notification: {
        title: "Hello, World!",
        content: "This is a notification",
        chime: ubo.Chime.CHIME_DONE,
        actions: {
          items: [
            {
              notificationDispatchItem: {
                storeAction: {
                  uboAction: {
                    audioPlayChimeAction: { name: "add" },
                  },
                },
                icon: "󰑣",
                color: "#ff0000",
                backgroundColor: "#00ff00",
              },
            },
          ],
        },
      },
    },
  },
});

// Make a unary RPC call
client.dispatchAction(request, (error: Error | null, response: any) => {
  if (error) {
    console.error("Error:", error);
    return;
  }
  console.log("Response:", response);
});

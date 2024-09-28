import * as grpc from "@grpc/grpc-js";
import * as protoLoader from "@grpc/proto-loader";
import { store } from "./generated/store/v1/store";
import { ubo } from "./generated/ubo/v1/ubo";

// Load the protobuf definitions
const packageDefinition = protoLoader.loadSync("store/v1/store.proto", {
  includeDirs: ["../../proto"],
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});
const protoDescriptor: any = grpc.loadPackageDefinition(packageDefinition);

// Replace 'your.package.name' with the actual package name defined in your .proto file
const StoreService = protoDescriptor.store.v1.StoreService;

// Create a client instance
const client = new StoreService(
  `${process.env.GRPC_HOST || "localhost"}:${process.env.GRPC_PORT || "50051"}`,
  grpc.credentials.createInsecure(),
) as store.v1.StoreServiceClient;

// Prepare the request
const request = new store.v1.DispatchActionRequest({
  action: new ubo.v1.Action({
    notifications_add_action: new ubo.v1.NotificationsAddAction({
      notification: new ubo.v1.Notification({
        title: "Hello",
        content: "World",
        color: "#ff0000",
      }),
    }),
  }),
});

// Make a unary RPC call
client.DispatchAction(
  request,
  (
    error: grpc.ServiceError | null,
    response: store.v1.DispatchActionResponse | undefined,
  ) => {
    if (error) {
      console.error("Error:", error);
      return;
    }
    if (!response) {
      console.error("No response");
      return;
    }
    console.log("Response:", response);
  },
);

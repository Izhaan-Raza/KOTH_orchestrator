// MongoDB seed script - insert users with crackable hashes
db = db.getSiblingDB('kothdb');

db.users.insertMany([
    {
        _id: 1,
        username: "mongouser",
        email: "mongouser@koth.local",
        // MD5 of "letmein" - reused for SSH access
        password: "0d107d09f5bbe40cade3de5c71e9e9b7",
        note: "Password is reused for SSH access",
        role: "operator",
        created: new Date()
    },
    {
        _id: 2,
        username: "admin",
        email: "admin@koth.local",
        // MD5 of "password123"
        password: "482c811da5d5b4bc6d497ffa98491e38",
        role: "user",
        created: new Date()
    },
    {
        _id: 3,
        username: "auditor",
        email: "audit@koth.local",
        // MD5 of "trustno1"
        password: "5fcfd41e547a12215b173ff47fdd3739",
        note: "Docker group membership beats password reuse",
        role: "analyst",
        created: new Date()
    }
]);

db.flags.insertOne({
    note: "Check /root/king.txt after getting root",
    hint: "Crack the SSH creds, log in as mongouser, then use the docker group via docker.sock"
});

print("MongoDB seeded successfully");

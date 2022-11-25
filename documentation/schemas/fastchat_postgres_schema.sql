CREATE TABLE "public.customers" (
	"uname" serial NOT NULL,
	"pub_key" TEXT NOT NULL,
	PRIMARY KEY ("uname")
);
CREATE TABLE "public.groups" (
	"group_id" integer NOT NULL,
	"uname" TEXT NOT NULL,
	"isAdmin" integer NOT NULL,
	PRIMARY KEY ("group_id","uname")
);

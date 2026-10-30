using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace GolfCoach.Api.Data.Migrations
{
    /// <inheritdoc />
    public partial class AddSwingAnalysis : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "SwingJson",
                table: "Analyses",
                type: "jsonb",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "SwingJson",
                table: "Analyses");
        }
    }
}
